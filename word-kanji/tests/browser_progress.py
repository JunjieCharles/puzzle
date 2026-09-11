"""Unlock-window and save migration checks using only synthetic puzzles/progress."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generator import Lexicon
from scripts.generate_two import puzzle_from, public_payload
from scripts.export_campaign import VERSION, public_record
from test_campaign import sample
from toy import toy
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:18743/puzzle/word-kanji/')
    url = parser.parse_args().url.rstrip('/') + '/'
    one = {'version': VERSION, 'revision': 'c' * 16,
           'puzzles': [public_record(sample(i, i, 1)) for i in range(8)]}
    rows, words = [], set()
    for i in range(8):
        chars = [chr(0x3400 + i * 8 + n) for n in range(8)]
        answer, clues = ''.join(chars[:2]), chars[2:]
        words.update(w for _, w in puzzle_from(clues).edge_words(answer))
        rows.append({'answer': answer, 'clues': clues, 'difficulty': [1] * 6})
    two = public_payload(rows, Lexicon([{'word': w, 'level': '1'} for w in words], set()))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)

        def context():
            ctx = browser.new_context(viewport={'width': 390, 'height': 844})
            ctx.route('**/campaign.json', lambda r: r.fulfill(json=one))
            ctx.route('**/campaign-two.json', lambda r: r.fulfill(json=two))
            return ctx

        for mode, suffix, key, data, answers in [
            ('campaign-one-standard', '', 'word-kanji:campaign', one, [toy(i) for i in range(8)]),
            ('campaign-two-standard', '-two', 'word-kanji:campaign-two', two, [r['answer'] for r in rows]),
        ]:
            ctx = context(); page = ctx.new_page(); errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(url + '#levels' + suffix)
            page.locator('#level-grid button').first.wait_for()
            assert page.locator('#level-grid button:not(:disabled)').count() == 3
            page.goto(url + '#play' + suffix + '/4')
            page.wait_for_url('**/#levels' + suffix)
            page.locator('#level-grid button').nth(2).click()
            assert page.locator('#reveal').is_hidden()
            assert page.locator('#review-next').is_disabled()
            for number, destination in [(3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 1), (1, 2), (2, None)]:
                page.wait_for_function("!document.querySelector('#entry').disabled")
                page.locator('#entry').fill(answers[number - 1]); page.locator('#submit').click()
                target = '#complete' + suffix if destination is None else f'#play{suffix}/{destination}'
                page.wait_for_url('**/' + target)
                if number == 3:
                    saved = json.loads(page.evaluate('(k) => localStorage.getItem(k)', key + ':v2'))
                    assert saved == {'revision': data['revision'], 'completed': 1, 'pending': [1, 2, 4]}
                    page.reload(); page.wait_for_function("!document.querySelector('#entry').disabled")
                    assert page.locator('#reveal').is_hidden()
                    page.goto(url + '#levels' + suffix)
                    page.locator('#level-grid button.passed').wait_for()
                    assert page.locator('#level-grid button.passed').all_text_contents() == ['3']
                    assert page.locator('#level-grid button:not(:disabled)').count() == 4
                    # Re-solving level 3 must not increment the count.
                    page.locator('#level-grid button').nth(2).click()
                    assert page.locator('#reveal').is_visible()
                    page.locator('#entry').fill(answers[2]); page.locator('#submit').click()
                    page.wait_for_url('**/#play' + suffix + '/4')
                    assert json.loads(page.evaluate('(k) => localStorage.getItem(k)', key + ':v2')) == saved
                if number == 8:
                    assert page.locator('#complete').is_hidden()
            saved = json.loads(page.evaluate('(k) => localStorage.getItem(k)', key + ':v2'))
            assert saved['completed'] == 8 and saved['pending'] == []
            assert not errors
            ctx.close()

            # Legacy local storage survives; v2 and independently progressed tabs union by level.
            ctx = context(); page = ctx.new_page(); page.goto(url)
            legacy = json.dumps({'revision': data['revision'], 'completed': 1})
            page.evaluate('([k,v]) => localStorage.setItem(k,v)', [key + ':v1', legacy])
            page.goto(url + '#levels' + suffix)
            page.locator('#level-grid button.passed').wait_for()
            assert page.locator('#level-grid button:not(:disabled)').count() == 4
            page.locator('#level-grid button').nth(2).click()
            stale = ctx.new_page(); stale.goto(url + '#play' + suffix + '/2')
            stale.wait_for_function("!document.querySelector('#entry').disabled")
            page.locator('#entry').fill(answers[2]); page.locator('#submit').click()
            page.wait_for_url('**/#play' + suffix + '/4')
            stale.locator('#entry').fill(answers[1]); stale.locator('#submit').click()
            stale.wait_for_url('**/#play' + suffix + '/4')
            record = json.loads(page.evaluate('(k) => localStorage.getItem(k)', key + ':v2'))
            assert record['completed'] == 3 and record['pending'] == [4, 5, 6]
            assert page.evaluate('(k) => localStorage.getItem(k)', key + ':v1') == legacy
            # Equal count but different passed sets must merge, not overwrite.
            code = page.evaluate("""async ([mode, revision]) => (await import('./save-code.js')).encodeSave({
                [mode]: {revision,completed:3,pending:[1,2,3]}})""", [mode, data['revision']])
            assert code.startswith('HT101-2.')
            page.locator('#save-open').click(); page.locator('#save-code').fill(code); page.locator('#save-import').click()
            page.wait_for_function("document.querySelector('#levels-count').textContent === '6 / 8'")
            record = json.loads(page.evaluate('(k) => localStorage.getItem(k)', key + ':v2'))
            assert record['completed'] == 6 and record['pending'] == [7, 8]
            page.locator('#save-export').click()
            page.wait_for_function("old => document.querySelector('#save-code').value !== old", arg=code)
            exported = page.locator('#save-code').input_value()
            fresh_ctx = context(); fresh = fresh_ctx.new_page(); fresh.goto(url)
            fresh.locator('#save-open').click(); fresh.locator('#save-code').fill(exported); fresh.locator('#save-import').click()
            fresh.wait_for_function('(k) => localStorage.getItem(k) !== null', arg=key + ':v2')
            assert json.loads(fresh.evaluate('(k) => localStorage.getItem(k)', key + ':v2')) == record
            fresh_ctx.close(); ctx.close()

        # Exhaustively round-trip reachable subsets, including total < 3 and final holes.
        ctx = context(); page = ctx.new_page(); page.goto(url)
        page.evaluate("""async () => {
            const {progressRecord, passedLevels, normalizeProgress, migrateProgress} = await import('./save-code.js');
            const revision = 'cccccccccccccccc';
            for (let total = 1; total <= 9; total++) for (let mask = 0; mask < 2 ** total; mask++) {
                const set = new Set(Array.from({length:total}, (_,i) => i+1).filter(n => mask & (1 << (n-1))));
                if ([...set].some(n => n > set.size+3)) continue;
                const record = progressRecord(set, total, revision);
                const restored = passedLevels(record, total);
                if (restored.size !== set.size || [...set].some(n => !restored.has(n))) throw Error('roundtrip');
            }
            for (const pending of [[1,1,3], [3,2,1], [0,2,3], [1,2,5], [1], [1,2,3,4], null]) {
                let rejected = false;
                try { normalizeProgress({revision,completed:1,pending},4); } catch { rejected = true; }
                if (!rejected) throw Error('malformed holes accepted');
            }
            const migrated = migrateProgress({revision:'cbe3a2f1ecd820a5',completed:198},'3a92ed63edc4ea56');
            const set = passedLevels(migrated,586);
            if (set.size !== 197 || !set.has(197) || set.has(198)) throw Error('old revision migration');
        }""")
        ctx.close(); browser.close()
    print('Progress checks passed: unlock +3, nonsequential passes, completion holes, legacy preservation, union, v2 roundtrip.')


if __name__ == '__main__':
    main()
