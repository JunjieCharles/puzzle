"""Analyze HSK paint masks using the frontend renderer; private details only."""
import argparse
import base64
import csv
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import threading
import zlib

import numpy as np
from scipy.spatial.distance import pdist, squareform
from playwright.sync_api import sync_playwright
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SIDE = 480
THRESHOLDS = [0, .01, .03, .05, .10]
POPCOUNT = np.array([i.bit_count() for i in range(256)], dtype=np.uint8)


def font_manifest(chars):
    """Record the local Thin files used by this Windows analysis environment."""
    paths = {'HarmonyOS Sans SC':ROOT/'public/fonts/HarmonyOS_Sans_SC_Thin.ttf'}
    result = {}
    for name,path in paths.items():
        with TTFont(path) as font:
            missing = sum(ord(c) not in font.getBestCmap() for c in chars)
            result[name] = {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                            'postscript_name':font['name'].getDebugName(6),
                            'version':font['name'].getDebugName(5),
                            'missing_glyphs':missing}
    return result


def private_path(path):
    path = path.resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError('Detailed analysis must remain outside the repository')
    return path


def close_pairs(masks, areas, max_distance=.1):
    """Exact full-resolution IoU, with a conservative block-area pruning bound.

    In each 20px block, abs(areaA-areaB) <= XOR pixels. Thus block L1
    never rejects a pair whose true IoU distance is within the tolerance.
    """
    if len(masks) < 2:
        return []
    blocks = np.array([m.reshape(24, 20, 24, 20).sum(axis=(1, 3)).ravel() for m in masks], dtype=np.float64)
    lower_xor = squareform(pdist(blocks, metric='cityblock'))
    sums = areas[:, None] + areas[None, :]
    lower_distance = 2 * lower_xor / (sums + lower_xor)
    candidates = np.argwhere(np.triu(lower_distance <= max_distance + 1e-12, 1))
    packed = np.packbits(np.array(masks).reshape(len(masks), -1), axis=1)
    pairs = []
    for i, j in candidates:
        xor = int(POPCOUNT[np.bitwise_xor(packed[i], packed[j])].sum())
        total = int(areas[i] + areas[j])
        distance = 2 * xor / (total + xor)
        if distance <= max_distance + 1e-12:
            pairs.append((int(i), int(j), distance))
    return pairs


def ambiguity(chars, pairs, words):
    rows = []
    for threshold in THRESHOLDS:
        neighbours = {c: {c} for c in chars}
        selected = [(i, j) for i, j, d in pairs if d <= threshold + 1e-12]
        for i, j in selected:
            neighbours[chars[i]].add(chars[j]); neighbours[chars[j]].add(chars[i])
        index = defaultdict(set)
        for i, word in enumerate(words):
            for pos, c in enumerate(word):
                index[(len(word), pos, c)].add(i)
        degrees = []
        length_counts = Counter()
        for i, word in enumerate(words):
            candidates = None
            for pos, c in enumerate(word):
                ids = set().union(*(index[(len(word), pos, other)] for other in neighbours[c]))
                candidates = ids if candidates is None else candidates & ids
                if len(candidates) <= 1:
                    break
            degree = len(candidates) - 1
            degrees.append(degree)
            if degree:
                length_counts[len(word)] += 1
        rows.append({'tolerance': threshold, 'character_pairs': len(selected),
                     'ambiguous_characters': sum(len(v) > 1 for v in neighbours.values()),
                     'max_character_alternatives': max((len(v)-1 for v in neighbours.values()), default=0),
                     'ambiguous_words': sum(d > 0 for d in degrees),
                     'word_pairs': sum(degrees)//2,
                     'ambiguous_words_by_length': dict(sorted(length_counts.items())),
                     'max_word_alternatives': max(degrees, default=0)})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lexicon', type=Path, default=REPO/'word-kanji/data/hsk-2025.json')
    parser.add_argument('--scope', choices=['hsk','extended'], default='extended')
    parser.add_argument('--extended-lexicon', type=Path, default=REPO/'word-kanji/public/endless-lexicon.json')
    parser.add_argument('--skip-similarity', action='store_true')
    parser.add_argument('--output', type=Path, default=REPO.parent/'puzzle-private/hanzi-paint-bucket/extended-analysis')
    args = parser.parse_args()
    output = private_path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    target = output/'analysis.sqlite'
    if target.exists() or (output/'analysis.partial.sqlite').exists():
        parser.error('Output already exists; select a new output directory')
    data = json.loads(args.lexicon.read_text(encoding='utf-8'))
    words = sorted({r['word'] for r in data['words']})
    if args.scope == 'extended':
        extended = json.loads(args.extended_lexicon.read_text(encoding='utf-8'))
        words = sorted(set(words) | set(extended['broad']))
    excluded_single = sum(len(w)==1 for w in words)
    words = [w for w in words if len(w)>=2]
    chars = sorted(set(''.join(words)))
    summary = {'standard': data['standard'], 'lexicon_sha256': hashlib.sha256(args.lexicon.read_bytes()).hexdigest(),
               'words': len(words), 'characters': len(chars), 'words_by_length': dict(sorted(Counter(map(len, words)).items())),
               'render': {'canvas': SIDE, 'font_size': 400, 'alpha_threshold': 128, 'connectivity': 4},
               'position_policy': 'fixed_canvas_only', 'scope':args.scope,
               'minimum_word_length':2,'excluded_single_character_entries':excluded_single,
               'similarity_computed':not args.skip_similarity,'fonts': {}}
    if args.scope == 'extended':
        summary['extended_lexicon_sha256'] = hashlib.sha256(args.extended_lexicon.read_bytes()).hexdigest()
        summary['extended_lexicon_version'] = extended['version']
    summary['font_sources'] = font_manifest(chars)
    spec = importlib.util.spec_from_file_location('paint_serve', ROOT/'scripts/serve.py')
    serve = importlib.util.module_from_spec(spec); spec.loader.exec_module(serve)
    server = serve.ThreadingHTTPServer(('127.0.0.1', 0), serve.PublicHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    db = sqlite3.connect(output/'analysis.partial.sqlite')
    db.executescript('''
        CREATE TABLE characters(font TEXT, character TEXT, region_count INTEGER, area_px INTEGER,
          canvas_ratio REAL, em_ratio REAL, component_areas_json TEXT, bbox_json TEXT,
          mask_zlib BLOB, PRIMARY KEY(font, character));
        CREATE TABLE eligible_words(font TEXT, word TEXT, PRIMARY KEY(font, word));
        CREATE TABLE similar_pairs(font TEXT, mode TEXT, character_a TEXT, character_b TEXT, iou_distance REAL);
        CREATE TABLE metadata(key TEXT PRIMARY KEY, value_json TEXT);
        CREATE TABLE missing_glyphs(font TEXT, character TEXT, PRIMARY KEY(font,character));
    ''')
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            summary['browser_version'] = browser.version
            page = browser.new_page()
            page.goto(f'http://127.0.0.1:{server.server_port}/puzzle/hanzi-paint-bucket/')
            page.wait_for_function("document.querySelectorAll('.status').length === 1 && [...document.querySelectorAll('.status')].every(x => !x.textContent.includes('…'))")
            if page.locator('.status.error').count():
                raise RuntimeError('HarmonyOS Sans SC Thin must load; no fallback is allowed')
            for font_index, font_name in enumerate(['HarmonyOS Sans SC']):
                print('Rendering', font_name, flush=True)
                masks, valid_chars, areas, region_counts = [], [], [], []
                with TTFont(ROOT/'public/fonts/HarmonyOS_Sans_SC_Thin.ttf') as font:
                    cmap = font.getBestCmap()
                supported = [c for c in chars if ord(c) in cmap]
                db.executemany('INSERT INTO missing_glyphs VALUES (?,?)',((font_name,c) for c in chars if ord(c) not in cmap))
                for start in range(0, len(supported), 64):
                    batch = page.evaluate('''async ({chars, fontIndex}) => {
                      const {analyzeGlyph} = await import('./app.js');
                      return chars.map(char => {
                        const {labels,count} = analyzeGlyph(char, `PaintFont${fontIndex}`, 250);
                        const packed = new Uint8Array(labels.length/8), areas = Array(count).fill(0);
                        let minX=480,minY=480,maxX=-1,maxY=-1;
                        for(let i=0;i<labels.length;i++) if(labels[i]>0) {
                          packed[i>>3] |= 1 << (7-(i&7)); areas[labels[i]-1]++;
                          const x=i%480,y=Math.floor(i/480); minX=Math.min(minX,x);minY=Math.min(minY,y);maxX=Math.max(maxX,x);maxY=Math.max(maxY,y);
                        }
                        return {packed:btoa(String.fromCharCode(...packed)),areas,bbox:count?[minX,minY,maxX+1,maxY+1]:null};
                      });
                    }''', {'chars': supported[start:start+64], 'fontIndex': font_index})
                    for char, row in zip(supported[start:start+64], batch):
                        packed = base64.b64decode(row['packed']); area = sum(row['areas'])
                        db.execute('INSERT INTO characters VALUES (?,?,?,?,?,?,?,?,?)',
                                   (font_name,char,len(row['areas']),area,area/SIDE**2,area/400**2,json.dumps(row['areas']),json.dumps(row['bbox']),zlib.compress(packed)))
                        if area:
                            if not args.skip_similarity:
                                masks.append(np.unpackbits(np.frombuffer(packed,dtype=np.uint8)).reshape(SIDE,SIDE).astype(bool))
                            valid_chars.append(char); areas.append(area); region_counts.append(len(row['areas']))
                valid_set = set(valid_chars)
                eligible = [w for w in words if all(c in valid_set for c in w)]
                db.executemany('INSERT INTO eligible_words VALUES (?,?)', ((font_name,w) for w in eligible))
                result = {'paintable_characters':len(valid_chars),'eligible_words':len(eligible),
                          'supported_characters':len(supported),'missing_characters':len(chars)-len(supported),
                          'supported_without_paint':len(supported)-len(valid_chars),
                          'eligible_words_by_length':dict(sorted(Counter(map(len,eligible)).items())),
                          'region_count_distribution':dict(sorted(Counter(region_counts).items())),
                          'positive_area_px_percentiles':dict(zip(['min','p25','median','p75','max'],np.percentile(areas,[0,25,50,75,100]).tolist())),
                          'tiny_total_area_below_25px':sum(a<25 for a in areas),'similarity':{}}
                result['area_sensitivity'] = []
                for minimum in [1,25,100,400]:
                    good = {c for c,a in zip(valid_chars,areas) if a >= minimum}
                    selected = [w for w in words if all(c in good for c in w)]
                    result['area_sensitivity'].append({'minimum_total_area_px':minimum,
                        'characters':len(good),'words':len(selected),
                        'two_character_words':sum(len(w)==2 for w in selected)})
                if not args.skip_similarity:
                    print('Comparing', font_name, 'fixed_canvas', flush=True)
                    pairs = close_pairs(masks, np.array(areas,dtype=np.int64))
                    result['similarity']['fixed_canvas'] = ambiguity(valid_chars,pairs,eligible)
                    db.executemany('INSERT INTO similar_pairs VALUES (?,?,?,?,?)',
                                   ((font_name,'fixed_canvas',valid_chars[i],valid_chars[j],d) for i,j,d in pairs))
                summary['fonts'][font_name]=result
                db.commit()
                print(json.dumps({'font':font_name,'paintable_characters':len(valid_chars),'eligible_words':len(eligible)}),flush=True)
            browser.close()
        db.execute('INSERT INTO metadata VALUES (?,?)',('summary',json.dumps(summary,ensure_ascii=False)))
        db.commit()
        with (output/'character-areas.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer = csv.writer(stream)
            cursor = db.execute('SELECT font,character,region_count,area_px,canvas_ratio,em_ratio,component_areas_json,bbox_json FROM characters ORDER BY font,character')
            writer.writerow([col[0] for col in cursor.description])
            writer.writerows(cursor)
        db.close()
        (output/'analysis.partial.sqlite').rename(target)
        (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('Analysis complete; detailed records saved outside repository.',flush=True)
    finally:
        db.close(); server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    main()
