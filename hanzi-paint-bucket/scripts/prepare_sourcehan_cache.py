"""Prepare private Light-font measurements and six-font consistency data."""
import hashlib
import html
import json
import sqlite3
import zlib

import numpy as np
from scipy import ndimage
from fontTools.ttLib import TTFont
from playwright.sync_api import sync_playwright

from game_font import ROOT, FAMILY, FILE
from analyze_multifont_similarity import font_sources, render_font
from build_idiom_bank import four_hanzi, private_path

PRIVATE=ROOT.parent.parent/'puzzle-private/hanzi-paint-bucket'
OUT=private_path(PRIVATE/'sourcehan-light-font-analysis')
RENDER={'canvas':480,'font_size':400,'alpha_threshold':128,'connectivity':4}


def write_report(output, counts, names):
    rows=[]
    for char, values in sorted(counts.items()):
        if len(set(values.get(name) for name in names)) == 1 and all(values.get(name) is not None for name in names):
            continue
        cells=''.join(f'<td>{values.get(name) if values.get(name) is not None else "?"}</td>' for name in names)
        rows.append(f'<tr><th>{html.escape(char)}</th>{cells}</tr>')
    headings=''.join(f'<th>{html.escape(name)}</th>' for name in names)
    document=f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>六字体连通块检查</title><h1>六字体连通块检查</h1><p>题面：思源黑体 CN Light。每块至少25像素；以下列出计数不一致或缺字的字。</p><table><thead><tr><th>字</th>{headings}</tr></thead><tbody>{"".join(rows)}</tbody></table></html>'
    (output/'report.html').write_text(document,encoding='utf-8')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    hsk_path=ROOT.parent/'word-kanji/data/hsk-2025.json'
    hsk={r['word'] for r in json.loads(hsk_path.read_text(encoding='utf-8'))['words']}
    broad=set(json.loads((ROOT.parent/'word-kanji/public/endless-lexicon.json').read_text(encoding='utf-8'))['broad'])
    idioms={r['word'].strip() for r in json.loads((PRIVATE/'idiom-source/idiom.json').read_text(encoding='utf-8')) if four_hanzi(r['word'].strip())}
    universe=idioms|{w for w in hsk|broad if len(w) in (2,3,4)}
    required=set(''.join(universe));hsk_chars=set(''.join(w for w in hsk if len(w) in (2,3,4)))
    cache=sqlite3.connect(OUT/'masks.sqlite')
    cache.executescript('CREATE TABLE IF NOT EXISTS masks(font TEXT,character TEXT,area INTEGER,mask BLOB,PRIMARY KEY(font,character));CREATE TABLE IF NOT EXISTS metadata(font TEXT PRIMARY KEY,value TEXT);')
    old=sqlite3.connect((PRIVATE/'multifont-position-v23/masks.sqlite').as_uri()+'?mode=ro',uri=True)
    for name,_,_ in font_sources('sourcehan')[1:]:
        cache.executemany('INSERT OR IGNORE INTO masks VALUES (?,?,?,?)',old.execute('SELECT * FROM masks WHERE font=?',(name,)))
        cache.executemany('INSERT OR IGNORE INTO metadata VALUES (?,?)',old.execute('SELECT * FROM metadata WHERE font=?',(name,)))
    cache.commit();old.close()
    sources={};coverage={}
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page();version=browser.version
        page.add_script_tag(content=(ROOT/'public/fill.mjs').read_text(encoding='utf-8').replace('export function','function'))
        page.add_script_tag(content='\n'.join(line for line in (ROOT/'public/glyph.mjs').read_text(encoding='utf-8').splitlines() if not line.startswith('import ')).replace('export function','function'))
        for name,path,face in font_sources('sourcehan'):
            coverage[name]=render_font(page,cache,name,path,face,required,version)
            sources[name]={'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_file':path.name,'face_index':face}
        browser.close()
    db=sqlite3.connect(OUT/'components.sqlite')
    db.executescript('CREATE TABLE IF NOT EXISTS components(character TEXT,font TEXT,count INTEGER,areas_json TEXT,PRIMARY KEY(character,font));CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value_json TEXT);')
    counts={c:{} for c in hsk_chars};glyphs=[]
    for name,_,_ in font_sources('sourcehan'):
        for c,area,packed in cache.execute('SELECT character,area,mask FROM masks WHERE font=?',(name,)):
            if c not in hsk_chars and name!=FAMILY:continue
            mask=np.unpackbits(np.frombuffer(zlib.decompress(packed),dtype=np.uint8)).reshape(480,480).astype(bool)
            labels,count=ndimage.label(mask);sizes=np.bincount(labels.ravel())[1:]
            if c in hsk_chars:
                effective=int((sizes>=25).sum());counts[c][name]=effective
                db.execute('INSERT OR REPLACE INTO components VALUES (?,?,?,?)',(c,name,effective,json.dumps(sizes.tolist())))
            if name==FAMILY:
                y,x=np.nonzero(mask);bbox=[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)] if area else None
                glyphs.append((name,c,count,area,area/480**2,area/400**2,json.dumps(sizes.tolist()),json.dumps(bbox),packed))
        for c in hsk_chars-coverage[name]:
            counts[c][name]=None;db.execute('INSERT OR REPLACE INTO components VALUES (?,?,NULL,NULL)',(c,name))
    names=list(sources)
    write_report(OUT,counts,names)
    missing={c for c,values in counts.items() if any(values.get(n) is None for n in names)}
    inconsistent={c for c,values in counts.items() if c not in missing and len(set(values.values()))>1}
    meta={'method':'six-font-paint-components-min25-v2-sourcehan','font_order':names,'fonts':sources,'render':RENDER,'browser_version':version,
          'hsk_sha256':hashlib.sha256(hsk_path.read_bytes()).hexdigest(),'minimum_component_area_px':25,'characters':len(hsk_chars),
          'inconsistent_characters':len(inconsistent),'missing_font_characters':len(missing)}
    db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('build',json.dumps(meta)));db.commit();db.close()
    (OUT/'summary.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    measure=sqlite3.connect(OUT/'measurements.sqlite')
    measure.executescript('CREATE TABLE IF NOT EXISTS characters(font TEXT,character TEXT PRIMARY KEY,region_count INTEGER,area_px INTEGER,canvas_ratio REAL,em_ratio REAL,component_areas_json TEXT,bbox_json TEXT,mask_zlib BLOB);CREATE TABLE IF NOT EXISTS stroke_metrics(character TEXT PRIMARY KEY,ink_area INTEGER,implied_area INTEGER,ratio REAL,ink_zlib BLOB,implied_zlib BLOB);')
    measure.executemany('INSERT OR REPLACE INTO characters VALUES (?,?,?,?,?,?,?,?,?)',glyphs);measure.commit();measure.close()
    seed=sqlite3.connect(OUT/'measurement-bank.sqlite');seed.execute('CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value_json TEXT)')
    seed.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('build',json.dumps({'font':FAMILY,'font_sha256':sources[FAMILY]['source_sha256'],'render':RENDER,'browser_version':version})));seed.commit();seed.close();cache.close()
    print(json.dumps(meta,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
