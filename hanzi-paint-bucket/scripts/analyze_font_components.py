"""Compare original enclosed-paint component counts across six local font faces."""
import argparse
import base64
from collections import Counter
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import threading

from fontTools.ttLib import TTFont
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
PRIVATE=REPO.parent/'puzzle-private/hanzi-paint-bucket'
RENDER={'canvas':480,'font_size':400,'alpha_threshold':128,'connectivity':4}


def inconsistent(counts):
    """Missing glyphs are unverifiable, not a zero-component glyph."""
    return all(c is not None for c in counts) and len(set(counts))>1


def finalize(out, areas, manifests, version, lexicon, chars, db):
    counts={c:{name:(None if values is None else sum(a>=25 for a in values)) for name,values in areas[c].items()} for c in chars}
    for c in chars:
        for name,count in counts[c].items():
            db.execute('UPDATE components SET count=? WHERE character=? AND font=?',(count,c,name))
    names=list(manifests)
    banned={c for c in chars if inconsistent(list(counts[c].values()))}
    missing={c for c in chars if any(v is None for v in counts[c].values())}
    with sqlite3.connect(PRIVATE/'hsk-combined-234-bank/bank.sqlite') as old:
        selected=[r[0] for r in old.execute('SELECT word FROM puzzles')]
    selected_chars=set(''.join(selected));affected=banned&selected_chars
    summary={'method':'six-font-paint-components-min25-v1','scope':'characters in HSK words of length 2/3/4',
        'hsk_sha256':hashlib.sha256(lexicon.read_bytes()).hexdigest(),'render':RENDER,'browser_version':version,
        'font_order':names,'fonts':manifests,'characters':len(chars),'inconsistent_characters':len(banned),
        'missing_font_characters':len(missing),'previous_bank_characters':len(selected_chars),
        'inconsistent_characters_in_previous_bank':len(affected),
        'previous_questions_containing_inconsistent_characters':sum(bool(set(w)&banned) for w in selected),
        'previous_affected_questions_by_length':dict(sorted(Counter(len(w) for w in selected if set(w)&banned).items())),
        'minimum_component_area_px':25,'small_components':'ignore enclosed components below 25 pixels; include exactly 25 pixels',
        'missing_policy':'unverifiable; separately excluded from question selection, never render using fallback'}
    rows=[{'character':c,'counts':counts[c],'areas':areas[c],'reason':'missing-font' if c in missing else 'inconsistent',
           'in_previous_bank':c in selected_chars} for c in chars if c in banned|missing]
    (out/'banned-characters.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('build',json.dumps(summary,ensure_ascii=False)))
    db.commit();db.close()
    if (out/'components.partial.sqlite').is_file():(out/'components.partial.sqlite').rename(out/'components.sqlite')
    header=''.join('<th>'+html.escape(n)+'</th>' for n in names)
    body=''.join('<tr><td>'+html.escape(r['character'])+'</td>'+''.join('<td>'+str(r['counts'][n] if r['counts'][n] is not None else '缺字')+'</td>' for n in names)+'<td>'+('是' if r['in_previous_bank'] else '')+'</td></tr>' for r in rows)
    document='<!doctype html><meta charset="utf-8"><title>字体连通块不一致字符</title><style>body{font-family:Microsoft YaHei,sans-serif;margin:32px;line-height:1.6}table{border-collapse:collapse}td,th{padding:6px 14px;border:1px solid #ddd}th{position:sticky;top:0;background:#eef3f0}td:first-child{font-size:24px}p{max-width:1100px;word-break:break-all}</style>'
    document+='<p>只统计面积≥25像素的四连通涂色区域；不计小于25像素的噪点。</p>'
    document+=f'<h1>六字体涂色连通块检查</h1><p>不一致字：{len(banned)}；当前题目受影响用字：{len(affected)}；缺字无法比较：{len(missing)}。</p>'
    document+='<h2>此前题库中的不一致字</h2><p>'+html.escape('、'.join(sorted(affected)))+'</p><h2>全部不一致字／缺字</h2><table><tr><th>字</th>'+header+'<th>此前题库使用</th></tr>'+body+'</table>'
    (out/'report.html').write_text(document,encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=PRIVATE/'font-component-analysis')
    parser.add_argument('--recount',action='store_true',help='Recount stored component areas at the 25-pixel threshold without rerendering')
    args=parser.parse_args();out=args.output.resolve()
    if out==REPO or REPO in out.parents:parser.error('Private analysis must be outside repository')
    if args.recount:
        db=sqlite3.connect(out/'components.sqlite')
        meta=json.loads(db.execute("SELECT value_json FROM metadata WHERE key='build'").fetchone()[0])
        lexicon=REPO/'word-kanji/data/hsk-2025.json'
        if hashlib.sha256(lexicon.read_bytes()).hexdigest()!=meta['hsk_sha256']:raise ValueError('HSK source changed')
        areas={}
        for c,name,raw in db.execute('SELECT character,font,areas_json FROM components'):
            areas.setdefault(c,{})[name]=json.loads(raw) if raw is not None else None
        finalize(out,areas,meta['fonts'],meta['browser_version'],lexicon,sorted(areas),db)
        return
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):parser.error('Use a new empty output directory')
    lexicon=REPO/'word-kanji/data/hsk-2025.json'
    entries=json.loads(lexicon.read_text(encoding='utf8'))['words']
    words={r['word'] for r in entries if len(r['word']) in (2,3,4)}
    chars=sorted(set(''.join(words)))
    local=Path(os.environ['LOCALAPPDATA'])/'Microsoft/Windows/Fonts'
    sources=[('Noto Sans SC',local/'NotoSansSCThin-5.ttf',None),
        ('MiSans',local/'MiSans-Thin.ttf',None),
        ('HarmonyOS Sans SC',ROOT/'public/fonts/HarmonyOS_Sans_SC_Thin.ttf',None),
        ('SimHei',Path('C:/Windows/Fonts/simhei.ttf'),None),
        ('Microsoft YaHei',Path('C:/Windows/Fonts/msyhl.ttc'),0),
        ('DengXian',Path('C:/Windows/Fonts/Dengl.ttf'),None)]
    manifests={};font_data={};coverage={}
    for name,path,face_index in sources:
        with TTFont(path,fontNumber=face_index if face_index is not None else -1) as font:
            manifest={'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_file':path.name,
                'face_index':face_index,'family':font['name'].getDebugName(1),'style':font['name'].getDebugName(2),
                'postscript_name':font['name'].getDebugName(6),'version':font['name'].getDebugName(5),
                'weight':font['OS/2'].usWeightClass}
            coverage[name]={c for c in chars if ord(c) in font.getBestCmap()}
            if face_index is not None:
                extracted=out/'Microsoft-YaHei-Light.ttf';font.save(extracted);data=extracted.read_bytes()
            else:data=path.read_bytes()
        manifest['render_file_sha256']=hashlib.sha256(data).hexdigest()
        manifest['missing_characters']=len(chars)-len(coverage[name]);manifests[name]=manifest
        font_data[name]=base64.b64encode(data).decode('ascii')
    spec=importlib.util.spec_from_file_location('components_serve',ROOT/'scripts/serve.py')
    serve=importlib.util.module_from_spec(spec);spec.loader.exec_module(serve)
    class QuietHandler(serve.PublicHandler):
        def log_message(self,*args):pass
    server=serve.ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    counts={c:{} for c in chars};areas={c:{} for c in chars}
    db=sqlite3.connect(out/'components.partial.sqlite')
    db.executescript('CREATE TABLE components(character TEXT,font TEXT,count INTEGER,areas_json TEXT,PRIMARY KEY(character,font));CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT);')
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page()
            version=browser.version
            page.goto(f'http://localhost:{server.server_port}/puzzle/hanzi-paint-bucket/lab.html')
            page.wait_for_function("document.querySelector('.status').textContent.includes('Thin 已加载')")
            for number,(name,_,_) in enumerate(sources):
                family=f'CountFont{number}';weight=manifests[name]['weight']
                awaitable=page.evaluate('''async ({family,weight,data})=>{
                  const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));
                  const face=new FontFace(family,bytes.buffer,{weight:String(weight)});
                  await face.load();document.fonts.add(face);return face.status;
                }''',{'family':family,'weight':weight,'data':font_data[name]})
                if awaitable!='loaded':raise ValueError('Font failed to load')
                supported=sorted(coverage[name])
                for start in range(0,len(supported),48):
                    batch=page.evaluate('''async ({chars,family,weight})=>{
                      const {analyzeGlyph}=await import('./app.js');
                      return chars.map(c=>{const {count,labels}=analyzeGlyph(c,family,weight);const areas=Array(count).fill(0);
                        for(const label of labels)if(label>0)areas[label-1]++;return {count,areas};});
                    }''',{'chars':supported[start:start+48],'family':family,'weight':weight})
                    for char,row in zip(supported[start:start+48],batch):
                        counts[char][name]=row['count'];areas[char][name]=row['areas']
                        db.execute('INSERT INTO components VALUES (?,?,?,?)',(char,name,row['count'],json.dumps(row['areas'])))
                    if start%480==0:print(f'{name}: {min(start+48,len(supported))}/{len(supported)}',flush=True)
                for char in set(chars)-coverage[name]:
                    counts[char][name]=None;areas[char][name]=None
                    db.execute('INSERT INTO components VALUES (?,?,NULL,NULL)',(char,name))
                db.commit()
            browser.close()
        finalize(out,areas,manifests,version,lexicon,chars,db)
    finally:
        db.close();server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
