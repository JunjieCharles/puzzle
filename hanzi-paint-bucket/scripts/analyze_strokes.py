"""Measure paint-implied ink area with the frontend rasterizer; private output."""
import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import threading
import zlib

import numpy as np
from scipy import ndimage
from skimage.morphology import medial_axis
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
METHOD='medial-axis-facing-paint-v1'


def implied_ink(ink,paint):
    """Assign ink pixels to local medial-axis sections facing painted whitespace."""
    ink=np.asarray(ink,dtype=bool);paint=np.asarray(paint,dtype=bool)
    if ink.shape!=paint.shape or np.any(ink & paint):
        raise ValueError('Ink and painted whitespace must be disjoint, same-sized masks')
    if not ink.any() or not paint.any():
        return np.zeros_like(ink)
    skeleton,radius=medial_axis(ink,return_distance=True,rng=0)
    distance_to_paint=ndimage.distance_transform_edt(~paint)
    facing=skeleton & (distance_to_paint<=radius+1)
    _,nearest=ndimage.distance_transform_edt(~skeleton,return_indices=True)
    return ink & facing[nearest[0],nearest[1]]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis',type=Path,default=REPO.parent/'puzzle-private/hanzi-paint-bucket/noto-extended-analysis/analysis.sqlite')
    parser.add_argument('--output',type=Path,default=REPO.parent/'puzzle-private/hanzi-paint-bucket/noto-stroke-analysis')
    args=parser.parse_args();out=args.output.resolve()
    if out==REPO or REPO in out.parents:parser.error('Output must be outside repository')
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):parser.error('Use a new empty output directory')
    lexicon=REPO/'word-kanji/data/hsk-2025.json'
    source=sqlite3.connect(args.analysis.resolve().as_uri()+'?mode=ro',uri=True)
    metadata=json.loads(source.execute("SELECT value_json FROM metadata WHERE key='summary'").fetchone()[0])
    source_masks={c:(area,zlib.decompress(packed)) for c,area,packed in source.execute('SELECT character,area_px,mask_zlib FROM characters')}
    entries=json.loads(lexicon.read_text(encoding='utf-8'))['words']
    words=[r['word'] for r in entries if len(r['word'])>=2 and all(source_masks.get(c,(0,))[0]>0 for c in r['word'])]
    chars=sorted(set(''.join(words)))
    spec=importlib.util.spec_from_file_location('paint_serve',ROOT/'scripts/serve.py')
    serve=importlib.util.module_from_spec(spec);spec.loader.exec_module(serve)
    server=serve.ThreadingHTTPServer(('127.0.0.1',0),serve.PublicHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    db=sqlite3.connect(out/'metrics.partial.sqlite')
    db.executescript('CREATE TABLE characters(character TEXT PRIMARY KEY,ink_area INTEGER,implied_area INTEGER,ratio REAL,ink_zlib BLOB,implied_zlib BLOB);CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT);')
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page()
            page.goto(f'http://localhost:{server.server_port}/puzzle/hanzi-paint-bucket/lab.html')
            page.wait_for_function("document.querySelector('.status').textContent.includes('Thin 已加载')")
            if browser.version!=metadata['browser_version']:raise ValueError('Browser version differs from paint analysis')
            for start in range(0,len(chars),32):
                batch=page.evaluate('''async chars=>{
                  const {analyzeGlyph}=await import('./app.js');
                  const pack=values=>{const p=new Uint8Array(values.length/8);for(let i=0;i<values.length;i++)if(values[i])p[i>>3]|=1<<(7-(i&7));return btoa(String.fromCharCode(...p));};
                  return chars.map(c=>{const {alpha,labels}=analyzeGlyph(c,'PaintFont0',200);return {ink:pack(alpha.map(a=>a>=128)),paint:pack(labels.map(a=>a>0))};});
                }''',chars[start:start+32])
                for char,row in zip(chars[start:start+32],batch):
                    raw=base64.b64decode(row['ink']);paint_raw=base64.b64decode(row['paint'])
                    if paint_raw!=source_masks[char][1]:raise ValueError('Rendering no longer matches stored paint masks')
                    ink=np.unpackbits(np.frombuffer(raw,dtype=np.uint8)).reshape(480,480).astype(bool)
                    paint=np.unpackbits(np.frombuffer(paint_raw,dtype=np.uint8)).reshape(480,480).astype(bool)
                    implied=implied_ink(ink,paint);total=int(ink.sum());area=int(implied.sum())
                    db.execute('INSERT INTO characters VALUES (?,?,?,?,?,?)',(char,total,area,area/total,zlib.compress(raw),zlib.compress(np.packbits(implied).tobytes())))
                if start%256==0:print(f'Measured {min(start+32,len(chars))}/{len(chars)} glyphs',flush=True)
            browser.close()
        summary={'method':METHOD,'characters':len(chars),'render':metadata['render'],
            'font_sha256':hashlib.sha256((ROOT/'public/fonts/NotoSansSC-Thin.ttf').read_bytes()).hexdigest(),
            'hsk_sha256':hashlib.sha256(lexicon.read_bytes()).hexdigest(),'browser_version':metadata['browser_version'],
            'method_details':'medial axis rng=0; facing iff distance to paint <= local ink radius + 1 raster px; ink assigned to nearest skeleton section; binary alpha>=128',
            'word_aggregation':'sum(implied ink pixels) / sum(all ink pixels)'}
        db.execute('INSERT INTO metadata VALUES (?,?)',('build',json.dumps(summary)))
        db.commit();db.close();(out/'metrics.partial.sqlite').rename(out/'metrics.sqlite')
        (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
        print('Stroke measurements complete',flush=True)
    finally:
        db.close();source.close();server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
