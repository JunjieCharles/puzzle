"""Local-only private bank preview. Never serve database files or cache answers."""
import argparse
import base64
import html
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit
import zlib

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
PREFIX='/puzzle/hanzi-paint-bucket/preview/'
PAGE_SIZE=12
MAX_PAGE_SIZE=24


def mask_png(packed,color=(239,182,65,255)):
    mask=np.unpackbits(np.frombuffer(zlib.decompress(packed),dtype=np.uint8)).reshape(480,480).astype(bool)
    image=np.zeros((480,480,4),dtype=np.uint8);image[mask]=color
    stream=BytesIO();Image.fromarray(image).save(stream,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode('ascii')


def handler_for(bank):
    with sqlite3.connect(bank.as_uri()+'?mode=ro',uri=True) as db:
        metadata=json.loads(db.execute("SELECT value_json FROM metadata WHERE key='build'").fetchone()[0])
    family=metadata.get('font','HarmonyOS Sans SC')
    font_file={'Source Han Sans CN':'SourceHanSansCN-Light.otf','Noto Sans SC':'NotoSansSC-Thin.ttf','HarmonyOS Sans SC':'HarmonyOS_Sans_SC_Thin.ttf'}[family]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def send_data(self,status,body=b'',mime='text/plain; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store, max-age=0')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; connect-src 'self'")
            self.end_headers();self.wfile.write(body)

        def do_GET(self):
            if self.headers.get('Host') not in {f'localhost:{self.server.server_port}',f'127.0.0.1:{self.server.server_port}'}:
                return self.send_data(403)
            if self.headers.get('Sec-Fetch-Site')=='cross-site':
                return self.send_data(403)
            url=urlsplit(self.path)
            if url.path==PREFIX.rstrip('/'):
                self.send_response(302);self.send_header('Location',PREFIX);self.send_header('Cache-Control','no-store');self.end_headers();return
            if not url.path.startswith(PREFIX):
                return self.send_data(404)
            name=url.path[len(PREFIX):]
            if name=='new-words':
                changes=bank.parent/'changes.json'
                if not changes.is_file():return self.send_data(404)
                words=json.loads(changes.read_text(encoding='utf-8'))['added']
                cards=[]
                with sqlite3.connect(bank.as_uri()+'?mode=ro',uri=True) as db:
                    rows=[(word,*db.execute('SELECT ordinal,hsk_level,total_paint_area_px FROM puzzles WHERE word=?',(word,)).fetchone()) for word in words]
                    rows.sort(key=lambda row:(-Fraction(row[3],len(row[0])),row[0]))
                    for word,ordinal,level,area in rows:
                        cells=[]
                        for i,char in enumerate(word,1):
                            packed=db.execute('SELECT mask_zlib FROM glyphs WHERE character=?',(char,)).fetchone()[0]
                            cells.append(f'<div class="glyph-cell"><img width="480" height="480" src="{mask_png(packed)}" alt="第{i}个字的涂色区域"></div>')
                        cards.append(f'<li class="card"><div class="card-top"><span>第 {ordinal} 题</span><span>HSK {html.escape(str(level))}</span></div><div class="glyphs">'+''.join(cells)+f'</div><div class="answer">{html.escape(word)}</div><div class="card-bottom">平均涂色面积 {area/len(word):,.1f} px²</div></li>')
                items=''.join(cards)
                document=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>新增题目 · 汉字油漆桶</title><link rel="stylesheet" href="./new-words.css"></head><body><main><a class="back" href="./">← 返回题库预览</a><header><p class="eyebrow">汉字油漆桶 · 本次题库更新</p><h1>新增题目 <span>{len(words)}</span></h1><p class="note">难度：简单 → 困难 · 每字平均涂色面积从大到小</p></header><ol>{items}</ol><footer>仅本机查看</footer></main></body></html>'''
                return self.send_data(200,document.encode('utf-8'),'text/html; charset=utf-8')
            if name=='font-report':
                folder='sourcehan-light-font-analysis' if family=='Source Han Sans CN' else 'font-component-analysis'
                report=REPO.parent/f'puzzle-private/hanzi-paint-bucket/{folder}/report.html'
                if not report.is_file():return self.send_data(404)
                return self.send_data(200,report.read_bytes(),'text/html; charset=utf-8')
            if name=='api':
                try:
                    query=parse_qs(url.query)
                    page=int(query.get('page',['1'])[0])
                    page_size=int(query.get('page_size',[str(PAGE_SIZE)])[0])
                except ValueError:
                    return self.send_data(400)
                if not 1<=page_size<=MAX_PAGE_SIZE:return self.send_data(400)
                with sqlite3.connect(bank.as_uri()+'?mode=ro',uri=True) as db:
                    build=json.loads(db.execute("SELECT value_json FROM metadata WHERE key='build'").fetchone()[0])
                    bank_type=build.get('bank_type','hsk')
                    total=db.execute('SELECT count(*) FROM puzzles').fetchone()[0]
                    pages=max(1,(total+page_size-1)//page_size)
                    if not 1<=page<=pages:return self.send_data(400)
                    rows=db.execute('SELECT ordinal,word,hsk_level,total_paint_area_px,total_ink_area,implied_ink_area,stroke_ratio FROM puzzles ORDER BY ordinal LIMIT ? OFFSET ?',(page_size,(page-1)*page_size)).fetchall()
                    items=[]
                    for ordinal,word,level,area,ink,implied,ratio in rows:
                        images=[mask_png(db.execute('SELECT mask_zlib FROM glyphs WHERE character=?',(c,)).fetchone()[0]) for c in word]
                        hints=[mask_png(db.execute('SELECT implied_zlib FROM stroke_metrics WHERE character=?',(c,)).fetchone()[0],(32,145,137,255)) for c in word]
                        ratios=[db.execute('SELECT implied_area * 1.0 / ink_area FROM stroke_metrics WHERE character=?',(c,)).fetchone()[0] for c in word]
                        character_areas=[db.execute('SELECT area_px FROM glyphs WHERE character=?',(c,)).fetchone()[0] for c in word]
                        items.append({'mean_paint_area_px':area/len(word),'character_areas':character_areas,'ordinal':ordinal,'word':word,'level':level,'area':area,'images':images,'hints':hints,'ink_area':ink,'implied_area':implied,'stroke_ratio':ratio,'character_ratios':ratios})
                return self.send_data(200,json.dumps({'page':page,'pages':pages,'page_size':page_size,'total':total,'items':items,'bank_type':bank_type,'font':family,'font_weight':build.get('font_weight',200),'font_style':build.get('font_style','Thin'),'difficulty_aggregation':build.get('difficulty_aggregation',''),'multifont_ambiguity':build.get('multifont_ambiguity_applied',False)},ensure_ascii=False).encode(),'application/json; charset=utf-8')
            files={'':(ROOT/'preview/index.html','text/html; charset=utf-8'),
                   'new-words.css':(ROOT/'preview/new-words.css','text/css; charset=utf-8'),
                   'style.css':(ROOT/'preview/style.css','text/css; charset=utf-8'),
                   'app.js':(ROOT/'preview/app.js','text/javascript; charset=utf-8'),
                   'font.ttf':(ROOT/'public/fonts'/font_file,'font/otf' if font_file.endswith('.otf') else 'font/ttf')}
            if name not in files:return self.send_data(404)
            path,mime=files[name];self.send_data(200,path.read_bytes(),mime)
    return Handler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank',type=Path)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--idioms',action='store_true',help='Preview the separate idiom bank (default port 8005)')
    mode.add_argument('--hsk-multi',action='store_true',help='Preview HSK 3+ bank (default port 8006)')
    parser.add_argument('--port',type=int)
    args=parser.parse_args()
    folder='hsk-multi-rectangles-bank' if args.hsk_multi else ('idiom-bank' if args.idioms else 'hsk-combined-editorial-v27-sourcehan-light-bank')
    bank=(args.bank or REPO.parent/f'puzzle-private/hanzi-paint-bucket/{folder}/bank.sqlite').resolve()
    port=args.port if args.port is not None else (8006 if args.hsk_multi else (8005 if args.idioms else 8004))
    if bank==REPO or REPO in bank.parents or not bank.is_file():
        parser.error('Bank must be an existing file outside repository')
    with ThreadingHTTPServer(('127.0.0.1',port),handler_for(bank)) as server:
        print(f'http://localhost:{server.server_port}{PREFIX}',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass


if __name__=='__main__':main()
