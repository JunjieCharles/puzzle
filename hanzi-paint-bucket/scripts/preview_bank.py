"""Local-only private bank preview. Never serve database files or cache answers."""
import argparse
import base64
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


def mask_png(packed,color=(239,182,65,255)):
    mask=np.unpackbits(np.frombuffer(zlib.decompress(packed),dtype=np.uint8)).reshape(480,480).astype(bool)
    image=np.zeros((480,480,4),dtype=np.uint8);image[mask]=color
    stream=BytesIO();Image.fromarray(image).save(stream,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode('ascii')


def handler_for(bank):
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
            if name=='font-report':
                report=REPO.parent/'puzzle-private/hanzi-paint-bucket/font-component-analysis/report.html'
                if not report.is_file():return self.send_data(404)
                return self.send_data(200,report.read_bytes(),'text/html; charset=utf-8')
            if name=='api':
                try:
                    page=int(parse_qs(url.query).get('page',['1'])[0])
                except ValueError:
                    return self.send_data(400)
                with sqlite3.connect(bank.as_uri()+'?mode=ro',uri=True) as db:
                    build=json.loads(db.execute("SELECT value_json FROM metadata WHERE key='build'").fetchone()[0])
                    bank_type=build.get('bank_type','hsk')
                    total=db.execute('SELECT count(*) FROM puzzles').fetchone()[0]
                    pages=max(1,(total+PAGE_SIZE-1)//PAGE_SIZE)
                    if not 1<=page<=pages:return self.send_data(400)
                    rows=db.execute('SELECT ordinal,word,hsk_level,total_paint_area_px,total_ink_area,implied_ink_area,stroke_ratio FROM puzzles ORDER BY ordinal LIMIT ? OFFSET ?',(PAGE_SIZE,(page-1)*PAGE_SIZE)).fetchall()
                    items=[]
                    for ordinal,word,level,area,ink,implied,ratio in rows:
                        images=[mask_png(db.execute('SELECT mask_zlib FROM glyphs WHERE character=?',(c,)).fetchone()[0]) for c in word]
                        hints=[mask_png(db.execute('SELECT implied_zlib FROM stroke_metrics WHERE character=?',(c,)).fetchone()[0],(32,145,137,255)) for c in word]
                        ratios=[db.execute('SELECT implied_area * 1.0 / ink_area FROM stroke_metrics WHERE character=?',(c,)).fetchone()[0] for c in word]
                        items.append({'ordinal':ordinal,'word':word,'level':level,'area':area,'images':images,'hints':hints,'ink_area':ink,'implied_area':implied,'stroke_ratio':ratio,'character_ratios':ratios})
                return self.send_data(200,json.dumps({'page':page,'pages':pages,'page_size':PAGE_SIZE,'total':total,'items':items,'bank_type':bank_type},ensure_ascii=False).encode(),'application/json; charset=utf-8')
            files={'':(ROOT/'preview/index.html','text/html; charset=utf-8'),
                   'style.css':(ROOT/'preview/style.css','text/css; charset=utf-8'),
                   'app.js':(ROOT/'preview/app.js','text/javascript; charset=utf-8'),
                   'font.ttf':(ROOT/'public/fonts/HarmonyOS_Sans_SC_Thin.ttf','font/ttf')}
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
    folder='hsk-multi-rectangles-bank' if args.hsk_multi else ('idiom-bank' if args.idioms else 'hsk-combined-editorial-v12-bank')
    bank=(args.bank or REPO.parent/f'puzzle-private/hanzi-paint-bucket/{folder}/bank.sqlite').resolve()
    port=args.port if args.port is not None else (8006 if args.hsk_multi else (8005 if args.idioms else 8004))
    if bank==REPO or REPO in bank.parents or not bank.is_file():
        parser.error('Bank must be an existing file outside repository')
    with ThreadingHTTPServer(('127.0.0.1',port),handler_for(bank)) as server:
        print(f'http://localhost:{server.server_port}{PREFIX}',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass


if __name__=='__main__':main()
