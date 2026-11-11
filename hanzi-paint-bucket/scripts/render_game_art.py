"""Render licensed font artwork in memory; never persist real-word glyph mappings."""
import base64
from pathlib import Path
from playwright.sync_api import sync_playwright
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

PUBLIC = Path(__file__).resolve().parents[1] / 'public'


def render_game_art(words):
    chars = sorted(set(''.join(words)))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page()
            page.add_script_tag(content=(PUBLIC / 'fill.mjs').read_text(encoding='utf-8').replace('export function', 'function'))
            source = (PUBLIC / 'glyph.mjs').read_text(encoding='utf-8')
            page.add_script_tag(content='\n'.join(line for line in source.splitlines() if not line.startswith('import ')).replace('export function', 'function'))
            measurements = page.evaluate('''async ({font,chars})=>{
              const data=Uint8Array.from(atob(font),c=>c.charCodeAt(0));
              const face=await new FontFace('Original',data,{weight:'200'}).load();document.fonts.add(face);
              return Object.fromEntries(chars.map(char=>{
                const ctx=document.createElement('canvas').getContext('2d');ctx.font='200 400px "Original"';
                const m=ctx.measureText(char),x=(480-m.actualBoundingBoxRight+m.actualBoundingBoxLeft)/2,y=(480+m.actualBoundingBoxAscent-m.actualBoundingBoxDescent)/2;
                let paint;
                if ('回答'.includes(char)) {
                  const rendered=analyzeGlyph(char,'Original',200), pixels=rendered.ctx.createImageData(480,480);
                  for(let i=0;i<rendered.labels.length;i++)if(rendered.labels[i]>0)pixels.data.set([239,182,65,255],i*4);
                  rendered.ctx.putImageData(pixels,0,0);paint=rendered.canvas.toDataURL('image/png');
                }
                return [char,{x,y,paint}];
              }));
            }''', {'font':base64.b64encode((PUBLIC / 'fonts/NotoSansSC-Thin.ttf').read_bytes()).decode(), 'chars':chars})
            result = {}
            with TTFont(PUBLIC / 'fonts/NotoSansSC-Thin.ttf') as font:
                cmap, glyphs = font.getBestCmap(), font.getGlyphSet()
                scale = 400 / font['head'].unitsPerEm
                for char in chars:
                    pen = SVGPathPen(glyphs)
                    glyphs[cmap[ord(char)]].draw(pen)
                    m = measurements[char]
                    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="480" viewBox="0 0 480 480"><path fill="#28434a" transform="translate({m["x"]} {m["y"]}) scale({scale} {-scale})" d="{pen.getCommands()}"/></svg>'
                    result[char] = {'strokes':'data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode(), 'paint':m.get('paint')}
            return result
        finally:
            browser.close()
