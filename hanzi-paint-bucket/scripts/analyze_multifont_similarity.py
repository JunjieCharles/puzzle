"""Private same-font ambiguity experiment with position-aware rectangles."""
import argparse
import base64
from collections import defaultdict
import hashlib
import html
import io
import json
import os
from pathlib import Path
import sqlite3
import zlib

import numpy as np
from fontTools.ttLib import TTFont
from playwright.sync_api import sync_playwright

from analyze_rectangle_similarity import ROOT, PRIVATE, rectangle_signature, rectangle_iou, rectangle_center_distance
from analyze_shift_similarity import translated_pairs
from build_idiom_bank import alternative_matches, private_path


def font_sources(primary='noto'):
    local = Path(os.environ['LOCALAPPDATA'])/'Microsoft/Windows/Fonts'
    from game_font import FAMILY, FILE
    first=(FAMILY,FILE,None) if primary=='sourcehan' else ('Noto Sans SC',ROOT/'public/fonts/NotoSansSC-Thin.ttf',None)
    return [first,
            ('MiSans', local/'MiSans-Thin.ttf', None),
            ('HarmonyOS Sans SC', ROOT/'public/fonts/HarmonyOS_Sans_SC_Thin.ttf', None),
            ('SimHei', Path('C:/Windows/Fonts/simhei.ttf'), None),
            ('Microsoft YaHei', Path('C:/Windows/Fonts/msyhl.ttc'), 0),
            ('DengXian', Path('C:/Windows/Fonts/Dengl.ttf'), None)]


def render_font(page, cache, name, path, face, required, version):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with TTFont(path, fontNumber=face if face is not None else -1) as font:
        supported = {c for c in required if ord(c) in font.getBestCmap()}
        weight = font['OS/2'].usWeightClass
        stream = io.BytesIO()
        font.save(stream)
    key = json.dumps({'sha': digest, 'face': face, 'browser': version, 'render': '480-400-alpha128-v1'})
    previous = cache.execute('SELECT value FROM metadata WHERE font=?', (name,)).fetchone()
    if previous and previous[0] != key:
        raise ValueError('Font cache fingerprint changed; use a new output directory')
    cache.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)', (name, key))
    existing = {r[0] for r in cache.execute('SELECT character FROM masks WHERE font=?', (name,))}
    pending = sorted(supported-existing)
    if pending:
        page.evaluate('''async ({data,weight})=>{
          const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));
          const face=await new FontFace('AnalysisFont',bytes,{weight:String(weight)}).load();
          document.fonts.clear();document.fonts.add(face);
        }''', {'data': base64.b64encode(stream.getvalue()).decode(), 'weight': weight})
        for start in range(0, len(pending), 64):
            chars = pending[start:start+64]
            packed = page.evaluate('''({chars,weight})=>chars.map(c=>{
              const {labels}=analyzeGlyph(c,'AnalysisFont',weight);
              const packed=new Uint8Array(labels.length/8);let area=0;
              for(let i=0;i<labels.length;i++)if(labels[i]>0){packed[i>>3]|=1<<(7-(i&7));area++;}
              return [area,btoa(String.fromCharCode(...packed))];
            })''', {'chars': chars, 'weight': weight})
            cache.executemany('INSERT INTO masks VALUES (?,?,?,?)',
                              [(name,c,r[0],zlib.compress(base64.b64decode(r[1]))) for c,r in zip(chars,packed)])
            cache.commit()
            if start % 1024 == 0:
                print(f'{name}: rendered {min(start+64,len(pending))}/{len(pending)}', flush=True)
    cache.commit()
    return supported


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank', type=Path, default=PRIVATE/'hsk-combined-editorial-v23-noto-bank/bank.sqlite')
    parser.add_argument('--output', type=Path, default=PRIVATE/'multifont-position-v23')
    args = parser.parse_args()
    output = private_path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.bank.resolve().as_uri()+'?mode=ro', uri=True) as db:
        targets = [r[0] for r in db.execute('SELECT word FROM puzzles ORDER BY ordinal')]
        competitors = [r[0] for r in db.execute('SELECT word FROM comparison_words')]
    hsk = {r['word'] for r in json.loads((ROOT.parent/'word-kanji/data/hsk-2025.json').read_text(encoding='utf-8'))['words']}
    required = set(''.join(competitors))
    queries = set(''.join(targets))
    cache = sqlite3.connect(output/'masks.sqlite')
    cache.executescript('CREATE TABLE IF NOT EXISTS masks(font TEXT,character TEXT,area INTEGER,mask BLOB,PRIMARY KEY(font,character));CREATE TABLE IF NOT EXISTS metadata(font TEXT PRIMARY KEY,value TEXT);')
    settings = [('pixel', None)] + [(f'rect95-center{limit}', limit) for limit in (30,40,50)]
    all_matches = {key:defaultdict(dict) for key,_ in settings}
    summaries, pair_examples = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page()
        page.add_script_tag(content=(ROOT/'public/fill.mjs').read_text(encoding='utf-8').replace('export function', 'function'))
        page.add_script_tag(content='\n'.join(line for line in (ROOT/'public/glyph.mjs').read_text(encoding='utf-8').splitlines() if not line.startswith('import ')).replace('export function','function'))
        for name,path,face in font_sources():
            supported = render_font(page,cache,name,path,face,required,browser.version)
            glyphs = {c:(name,c,0,area,packed) for c,area,packed in cache.execute('SELECT character,area,mask FROM masks WHERE font=?',(name,))}
            areas = {c:r[3] for c,r in glyphs.items()}
            eligible = [w for w in competitors if set(w)<=supported]
            target = [w for w in targets if set(w)<=supported]
            raw, normalized = {}, {}
            for c,r in glyphs.items():
                mask = np.unpackbits(np.frombuffer(zlib.decompress(r[-1]),dtype=np.uint8)).reshape(480,480).astype(bool)
                boxes = rectangle_signature(mask, normalize=False)
                if boxes is not None:
                    raw[c] = boxes
                    low = boxes[:,:2].min(axis=0)
                    size = boxes[:,2:].max(axis=0)-low
                    normalized[c] = (boxes-np.tile(low,2))/np.tile(size,2)
            rect_pairs = []
            for a in sorted(queries & raw.keys()):
                for b in raw:
                    if a==b or (b in queries and b<a):
                        continue
                    distance = rectangle_center_distance(raw[a],raw[b])
                    if distance>50:
                        continue
                    score = rectangle_iou(normalized[a],normalized[b])
                    if score>.95:
                        rect_pairs.append((a,b,score,distance))
            pixel_path = output/(name.replace(' ','-')+'-pixel.json')
            fingerprint = hashlib.sha256((json.dumps(sorted(queries))+cache.execute('SELECT value FROM metadata WHERE font=?',(name,)).fetchone()[0]+json.dumps(sorted(supported))).encode()).hexdigest()
            saved = json.loads(pixel_path.read_text(encoding='utf-8')) if pixel_path.exists() else None
            if saved and saved['fingerprint']==fingerprint:
                pixel = saved['pairs']
            else:
                print(name+': computing pixel similarities',flush=True)
                pixel,_ = translated_pairs(glyphs,queries,.95,10)
                pixel_path.write_text(json.dumps({'fingerprint':fingerprint,'pairs':pixel},ensure_ascii=False),encoding='utf-8')
            for key,limit in settings:
                pairs = pixel + [(a,b) for a,b,score,distance in rect_pairs if limit is not None and distance<=limit]
                words,matches = alternative_matches(eligible,target,areas,pairs)
                affected = 0
                for word,ids in matches.items():
                    alternatives = [words[i] for i in ids if words[i]!=word]
                    if alternatives:
                        affected += 1
                        for alt in alternatives:
                            changes = []
                            for a,b in zip(word,alt):
                                if a==b:continue
                                is_rect = a in raw and b in raw
                                changes.append({'a':a,'b':b,'rectangle_iou':rectangle_iou(normalized[a],normalized[b]) if is_rect else None,
                                                'center_l1':rectangle_center_distance(raw[a],raw[b]) if is_rect else None})
                            all_matches[key][word].setdefault(alt,[]).append({'font':name,'changes':changes})
                summaries.append({'font':name,'setting':key,'affected':affected,'missing_characters':len(required-supported),'unverifiable_questions':len(targets)-len(target)})
            # User-supplied diagnostic pairs; no real question mapping in stdout.
            for a,b in [('首','想'),('谋','偷'),('星','显'),('谋','提'),('旗','道')]:
                is_rect = a in raw and b in raw
                pair_examples.append({'font':name,'pair':a+b,'rectangle_iou':rectangle_iou(normalized[a],normalized[b]) if is_rect else None,
                                      'center_l1':rectangle_center_distance(raw[a],raw[b]) if is_rect else None,
                                      'pixel_match':any({r[0],r[1]}=={a,b} for r in pixel)})
            print(json.dumps({'font':name,'status':'complete','settings':summaries[-len(settings):]},ensure_ascii=False),flush=True)
        browser.close()
    cache.close()
    combined = []
    for key,_ in settings:
        matches = all_matches[key]
        combined.append({'setting':key,'affected':len(matches),'with_hsk_alternative':sum(any(a in hsk for a in alts) for alts in matches.values()),'remaining_without_refill':len(targets)-len(matches)})
    summary = {'questions':len(targets),'comparison_words':len(competitors),'fonts':6,
               'semantics':'one same font must match every position of a complete alternative word; union over fonts, never mix per-position fonts',
               'rectangle_threshold_exclusive':.95,'center_distance_inclusive':True,'per_font':summaries,'combined':combined}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'details.json').write_text(json.dumps(all_matches,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'diagnostic-pairs.json').write_text(json.dumps(pair_examples,ensure_ascii=False,indent=2),encoding='utf-8')
    sections = []
    for key,_ in settings:
        rows=[]
        for word,alternatives in sorted(all_matches[key].items(),key=lambda r:not any(a in hsk for a in r[1])):
            choices=[]
            for alt,evidence in alternatives.items():
                descriptions=[]
                for e in evidence:
                    changes=', '.join(html.escape(c['a']+'↔'+c['b'])+(f" 矩形{c['rectangle_iou']:.2%} / 中心距离{c['center_l1']:g}px" if c['rectangle_iou'] is not None else ' 像素或空白匹配') for c in e['changes'])
                    descriptions.append(html.escape(e['font'])+'：'+changes)
                choices.append(html.escape(alt)+('【HSK】' if alt in hsk else '【扩展】')+'<details><summary>命中字体验证</summary>'+'<br>'.join(descriptions)+'</details>')
            rows.append('<tr><td>'+html.escape(word)+'</td><td>'+'<br>'.join(choices)+'</td></tr>')
        sections.append('<h2>'+key+f'：{len(rows)} 题</h2><table><tr><th>当前题目</th><th>替代词及证据</th></tr>'+''.join(rows)+'</table>')
    (output/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>位置约束与六字体多解试验</title><style>body{font:16px/1.7 sans-serif;max-width:1200px;margin:30px auto}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:10px;text-align:left}details{font-size:14px;color:#456}</style><h1>位置约束与六字体多解试验</h1><p>两边同字体，整词须在至少一种字体内逐位匹配；不混搭字体。保留原像素规则，矩形 IoU &gt;95%，中心距离分别≤30/40/50px。只分析当前题目，不补题、不发布。</p>'+''.join(sections),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
