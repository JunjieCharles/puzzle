"""Build private idiom or HSK 3+ character banks, including blank glyphs."""
import argparse
import base64
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import threading
import uuid
import zlib

import numpy as np
from scipy import ndimage
from fontTools.ttLib import TTFont
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
PRIVATE=REPO.parent/'puzzle-private/hanzi-paint-bucket'


def module(name):
    spec=importlib.util.spec_from_file_location('idiom_'+name,ROOT/'scripts'/f'{name}.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


bank=module('build_hsk_bank')
strokes=module('analyze_strokes')


def private_path(path):
    path=path.resolve()
    if path==REPO or REPO in path.parents:
        raise ValueError('Private idiom data must remain outside repository')
    return path


def four_hanzi(word):
    return len(word)==4 and all('\u3400'<=c<='\u9fff' or '\uf900'<=c<='\ufaff' or 0x20000<=ord(c)<=0x323af for c in word)


def idiom_candidates(words, glyphs, rectangles):
    supported=[w for w in sorted(set(words)) if all(c in glyphs for c in w)]
    painted=[w for w in supported if sum(glyphs[c][3]>0 for c in w)>=2]
    # Truly blank glyphs are permitted. Nonempty but microscopic glyphs are not
    # silently erased: the existing 25-pixel admission rule still applies.
    visible=[w for w in painted if all(glyphs[c][3]==0 or max(json.loads(glyphs[c][6]),default=0)>=25 for c in w)]
    shaped=[w for w in visible if not set(w)&rectangles]
    return shaped,{'four_character_idioms':len(set(words)), 'font_supported_idioms':len(supported),
        'excluded_unsupported_idioms':len(set(words))-len(supported),'at_least_two_painted':len(painted),
        'excluded_tiny_region_words':len(painted)-len(visible),'after_minimum_region_filter':len(visible),
        'excluded_single_rectangle_words':len(visible)-len(shaped),'after_shape_filter':len(shaped)}


def alternative_matches(competitors, targets, areas, pairs):
    """Exact word candidates under pairwise similarity; blank matches blank only.

    Return IDs of all matching words, including the target. Do not collapse words
    with identical blank patterns or take transitive closure of shape similarity.
    """
    words=sorted(set(competitors));word_set=set(words)
    chars=set(''.join(words));neighbors={c:{c} for c in chars if areas[c]>0}
    for a,b,*_ in pairs:
        if a in neighbors and b in neighbors:
            neighbors[a].add(b);neighbors[b].add(a)
    index=defaultdict(set)
    for i,w in enumerate(words):
        for pos,c in enumerate(w):
            index[(len(w),pos,c if areas[c]>0 else None)].add(i)
    result={}
    for word in targets:
        if word not in word_set:raise ValueError('Target absent from comparison universe')
        options=[]
        for pos,c in enumerate(word):
            if areas[c]==0:
                ids=index[(len(word),pos,None)]
            else:
                ids=set().union(*(index[(len(word),pos,n)] for n in neighbors[c]))
            options.append(ids)
        options.sort(key=len)
        matches=options[0].copy()
        for ids in options[1:]:matches.intersection_update(ids)
        result[word]=sorted(matches)
    return words,result


def select_disjoint(words, scores, per_length=False, scope_by_length=None):
    """Hardest first within each character-use scope; globally mixed display order."""
    used=defaultdict(set);selected=[]
    for w in sorted(words,key=lambda w:(scores[w],w)):
        scope=scope_by_length[len(w)] if scope_by_length is not None else (len(w) if per_length else 0)
        if used[scope].isdisjoint(w):
            selected.append(w);used[scope].update(w)
    selected.sort(key=lambda w:(-scores[w],w))
    return selected,set().union(*used.values()) if used else set()


def is_day_shaped(mask, font_size=400):
    """Two vertically stacked solid boxes, ignoring regions below 25 px.

    Default geometry: corresponding x edges within 1% of font size and
    vertical separation no larger than 8%. Only classifies whole glyphs.
    """
    labels,count=bank.ndimage.label(mask)
    sizes=np.bincount(labels.ravel(),minlength=count+1)
    components=[labels==i for i in range(1,count+1) if sizes[i]>=25]
    if len(components)!=2 or not all(bank.is_single_solid_rectangle(m,font_size) for m in components):
        return False
    boxes=[]
    for m in components:
        y,x=np.nonzero(m);boxes.append((int(y.min()),int(y.max()),int(x.min()),int(x.max())))
    a,b=sorted(boxes)
    return (0<b[0]-a[1]-1<=font_size*.08
            and abs(a[2]-b[2])<=font_size*.01 and abs(a[3]-b[3])<=font_size*.01)


def word_pattern_excluded(word, areas, day_characters):
    if len(word)==4 and (all(areas[c]==0 for c in word[:2]) or all(areas[c]==0 for c in word[2:])):
        return True
    return len(word)==2 and all(c in day_characters for c in word)


def informative_count(word, glyphs, rectangles):
    return sum(glyphs[c][3]>0 and c not in rectangles for c in word)


def combined_eligible(word, glyphs, rectangles):
    return (len(word) in (2,3,4) and informative_count(word,glyphs,rectangles)>=2
            and (len(word)!=3 or all(glyphs[c][3]>0 for c in word)))


def font_component_exclusions(path, required, hsk_hash, font_hash, render_meta, browser_version):
    path=private_path(path)
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        meta=json.loads(db.execute("SELECT value_json FROM metadata WHERE key='build'").fetchone()[0])
        if (meta['hsk_sha256']!=hsk_hash or meta['render']!=render_meta or meta['browser_version']!=browser_version
            or meta.get('minimum_component_area_px')!=25 or meta['fonts']['HarmonyOS Sans SC']['source_sha256']!=font_hash):
            raise ValueError('Six-font component analysis differs from current sources or noise rule')
        names=set(meta['font_order'])
        if names!={'Noto Sans SC','MiSans','HarmonyOS Sans SC','SimHei','Microsoft YaHei','DengXian'}:
            raise ValueError('Six expected font families required')
        counts={}
        for c,name,count,raw in db.execute('SELECT character,font,count,areas_json FROM components'):
            if raw is not None and count!=sum(a>=25 for a in json.loads(raw)):
                raise ValueError('Component counts do not follow the 25-pixel noise rule')
            counts.setdefault(c,{})[name]=count
    if any(set(counts.get(c,{}))!=names for c in required):raise ValueError('Six-font analysis lacks source characters')
    missing={c for c in required if any(n is None for n in counts[c].values())}
    banned={c for c in required-missing if len(set(counts[c].values()))>1}
    return banned,missing,meta


def render(chars, glyphs, metrics, browser_version, require_metrics=False):
    """Shared browser rasterization; compare every cached paint mask byte-for-byte."""
    if not chars:return browser_version
    serve=module('serve')
    class QuietHandler(serve.PublicHandler):
        def log_message(self,*args):pass
    server=serve.ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True);page=browser.new_page()
            if browser_version and browser.version!=browser_version:
                raise ValueError('Browser version differs from cached analysis')
            browser_version=browser.version
            page.goto(f'http://localhost:{server.server_port}/puzzle/hanzi-paint-bucket/')
            page.wait_for_function("document.querySelector('.status').textContent.includes('Thin 已加载')")
            for start in range(0,len(chars),32):
                batch=page.evaluate('''async chars=>{
                  const {analyzeGlyph}=await import('./app.js');
                  const pack=values=>{const p=new Uint8Array(values.length/8);for(let i=0;i<values.length;i++)if(values[i])p[i>>3]|=1<<(7-(i&7));return btoa(String.fromCharCode(...p));};
                  return chars.map(c=>{const {alpha,labels}=analyzeGlyph(c,'PaintFont0',250);return {ink:pack(alpha.map(a=>a>=128)),paint:pack(labels.map(a=>a>0))};});
                }''',chars[start:start+32])
                for char,row in zip(chars[start:start+32],batch):
                    ink_raw=base64.b64decode(row['ink']);paint_raw=base64.b64decode(row['paint'])
                    paint=np.unpackbits(np.frombuffer(paint_raw,dtype=np.uint8)).reshape(480,480).astype(bool)
                    if char in glyphs:
                        if paint_raw!=zlib.decompress(glyphs[char][-1]):raise ValueError('Cached paint differs from renderer')
                    else:
                        labels,count=ndimage.label(paint);sizes=np.bincount(labels.ravel())[1:];area=int(paint.sum())
                        y,x=np.nonzero(paint)
                        bbox=[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)] if area else None
                        glyphs[char]=(bank.FONT,char,count,area,area/480**2,area/400**2,json.dumps(sizes.tolist()),json.dumps(bbox),zlib.compress(paint_raw))
                    if require_metrics:
                        ink=np.unpackbits(np.frombuffer(ink_raw,dtype=np.uint8)).reshape(480,480).astype(bool)
                        implied=strokes.implied_ink(ink,paint);total=int(ink.sum());area=int(implied.sum())
                        if total==0:raise ValueError('Supported character rendered without ink')
                        metrics[char]=(char,total,area,area/total,zlib.compress(ink_raw),zlib.compress(np.packbits(implied).tobytes()))
                if start%256==0:print(f'Rendered {min(start+32,len(chars))}/{len(chars)} glyphs; ink metrics={require_metrics}',flush=True)
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()
    return browser_version


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=PRIVATE/'idiom-source/idiom.json')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--hsk-multi',action='store_true',help='Historical HSK length >=3 bank')
    mode.add_argument('--hsk-combined',action='store_true',help='HSK length 2/3/4; two informative glyphs; no blanks in length 3; lengths 2/3 share characters, length 4 separate')
    parser.add_argument('--font-component-analysis',type=Path,default=PRIVATE/'font-component-analysis/components.sqlite')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--policy',type=Path,default=PRIVATE/'vocabulary-policy.json',help='Private policy; alternate files allow isolated what-if builds')
    args=parser.parse_args();source=private_path(args.source)
    is_hsk=args.hsk_multi or args.hsk_combined
    output=private_path(args.output or PRIVATE/('hsk-combined-editorial-v12-bank' if args.hsk_combined else 'hsk-multi-rectangles-bank' if args.hsk_multi else 'idiom-bank'))
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):parser.error('Use a new empty output directory')
    raw=source.read_bytes();entries=json.loads(raw)
    idioms={r['word'].strip() for r in entries if four_hanzi(r['word'].strip())}
    hsk_path=REPO/'word-kanji/data/hsk-2025.json';extended_path=REPO/'word-kanji/public/endless-lexicon.json'
    hsk_entries=json.loads(hsk_path.read_text(encoding='utf8'))['words']
    levels={r['word']:r['level'] for r in hsk_entries}
    hsk=set(levels)
    broad=set(json.loads(extended_path.read_text(encoding='utf8'))['broad'])
    source_words={w for w in hsk if len(w)>=3} if args.hsk_multi else idioms
    universe=sorted(idioms|{w for w in hsk|broad if (len(w)>=3 if args.hsk_multi else four_hanzi(w))})
    if args.hsk_combined:
        source_words={w for w in hsk if len(w) in (2,3,4)}
        universe=sorted(idioms|{w for w in hsk|broad if len(w) in (2,3,4)})
    required=set(''.join(universe))
    font_path=ROOT/'public/fonts/HarmonyOS_Sans_SC_Thin.ttf';font_hash=hashlib.sha256(font_path.read_bytes()).hexdigest()
    with TTFont(font_path) as font:supported={c for c in required if ord(c) in font.getBestCmap()}
    with sqlite3.connect(PRIVATE/'extended-analysis/analysis.sqlite') as db:
        metadata=json.loads(db.execute("SELECT value_json FROM metadata WHERE key='summary'").fetchone()[0])
        if metadata['font_sources'][bank.FONT]['sha256']!=font_hash:raise ValueError('Cached font differs')
        glyphs={r[1]:r for r in db.execute('SELECT * FROM characters WHERE font=?',(bank.FONT,)) if r[1] in supported}
    with sqlite3.connect(PRIVATE/'stroke-analysis/metrics.sqlite') as db:
        stroke_meta=json.loads(db.execute("SELECT value_json FROM metadata WHERE key='build'").fetchone()[0])
        if (stroke_meta['font_sha256']!=font_hash or stroke_meta['browser_version']!=metadata['browser_version']
            or stroke_meta['render']!=metadata['render']):raise ValueError('Cached strokes differ')
        metrics={r[0]:r for r in db.execute('SELECT * FROM characters') if r[0] in supported}
    if is_hsk and (PRIVATE/'idiom-bank/measurements.sqlite').is_file():
        with sqlite3.connect(PRIVATE/'idiom-bank/bank.sqlite') as db:
            cache_meta=json.loads(db.execute("SELECT value_json FROM metadata WHERE key='build'").fetchone()[0])
        if any(cache_meta[k]!=v for k,v in {'font_sha256':font_hash,'browser_version':metadata['browser_version'],'render':metadata['render']}.items()):
            raise ValueError('Idiom measurement cache fingerprint differs')
        with sqlite3.connect(PRIVATE/'idiom-bank/measurements.sqlite') as db:
            glyphs.update({r[1]:r for r in db.execute('SELECT * FROM characters') if r[1] in supported})
            metrics.update({r[0]:r for r in db.execute('SELECT * FROM stroke_metrics') if r[0] in supported})
    render(sorted(supported-glyphs.keys()),glyphs,metrics,metadata['browser_version'])
    competitors=[w for w in universe if all(c in supported for c in w)]
    areas={c:r[3] for c,r in glyphs.items()}
    rectangles={c for c,r in glyphs.items() if r[3]>0 and bank.is_single_solid_rectangle(np.unpackbits(np.frombuffer(zlib.decompress(r[-1]),dtype=np.uint8)).reshape(480,480))}
    moon_characters=set();kai_characters=set()
    if args.hsk_combined:
        structural=module('component_shapes')
        graph=structural.load_components(PRIVATE/'structure-source/ids.txt')
        moon_characters,kai_characters=structural.structural_paint_classes(
            set(''.join(source_words)),{c:json.loads(r[6]) for c,r in glyphs.items()},graph)
        rectangles.update(kai_characters)
    shaped,summary=idiom_candidates(source_words,glyphs,set() if is_hsk else rectangles)
    summary['single_rectangle_exclusion_applied']=not is_hsk
    if args.hsk_combined:
        summary.update({'moon_only_shape_characters':len(moon_characters),
            'kai_single_rectangle_characters':len(kai_characters),
            'structural_ids_sha256':structural.IDS_SHA256})
        eligible=[w for w in shaped if informative_count(w,glyphs,rectangles)>=2]
        summary['excluded_fewer_than_two_nonrectangle_words']=len(shaped)-len(eligible)
        summary['after_informative_glyph_filter']=len(eligible)
        shaped=[w for w in eligible if combined_eligible(w,glyphs,rectangles)]
        summary['excluded_three_character_words_with_blank']=len(eligible)-len(shaped)
        summary['after_three_character_blank_filter']=len(shaped)
    if is_hsk:
        for old,new in [('four_character_idioms','hsk_two_to_four_words' if args.hsk_combined else 'hsk_three_plus_words'),('font_supported_idioms','font_supported_words'),('excluded_unsupported_idioms','excluded_unsupported_words')]:
            summary[new]=summary.pop(old)
    font_banned=set();font_missing=set()
    if args.hsk_combined:
        font_banned,font_missing,font_meta=font_component_exclusions(args.font_component_analysis,
            set(''.join(source_words)),hashlib.sha256(hsk_path.read_bytes()).hexdigest(),font_hash,
            metadata['render'],metadata['browser_version'])
        consistent=[w for w in shaped if not set(w)&(font_banned|font_missing)]
        summary.update({'font_component_consistency_applied':True,'font_component_minimum_area_px':25,
            'font_component_method':font_meta['method'],'font_component_families':font_meta['font_order'],
            'font_component_analysis_sha256':hashlib.sha256(args.font_component_analysis.read_bytes()).hexdigest(),
            'font_inconsistent_characters_in_hsk':len(font_banned),'font_missing_characters_in_hsk':len(font_missing),
            'excluded_font_inconsistency_words':len(shaped)-len(consistent),'after_font_consistency_filter':len(consistent)})
        shaped=consistent
    policy_path=private_path(args.policy)
    policy=json.loads(policy_path.read_text(encoding='utf8'))
    excluded=bank.policy_module.editorial_exclusions(hsk_entries,policy)
    summary['excluded_editorial_words']=sum(w in excluded for w in shaped)
    shaped=[w for w in shaped if w not in excluded]
    summary['after_editorial_filter']=len(shaped)
    if args.hsk_combined:
        scoped_excluded,scoped_characters=bank.policy_module.two_character_component_exclusions(
            shaped,policy,{c:json.loads(r[6]) for c,r in glyphs.items()})
        shaped=[w for w in shaped if w not in scoped_excluded]
        summary.update({'two_character_structural_banned_characters':len(scoped_characters),
            'excluded_two_character_structural_words':len(scoped_excluded),
            'after_two_character_structural_filter':len(shaped)})
        day_characters={c for c in set(''.join(shaped)) if is_day_shaped(
            np.unpackbits(np.frombuffer(zlib.decompress(glyphs[c][-1]),dtype=np.uint8)).reshape(480,480))}
        day_characters.update(moon_characters)
        filtered=[w for w in shaped if not word_pattern_excluded(w,areas,day_characters)]
        summary.update({'excluded_word_pattern_words':len(shaped)-len(filtered),
            'after_word_pattern_filter':len(filtered),'day_shape_character_count':len(day_characters)})
        shaped=filtered
    print(json.dumps(summary),flush=True)
    # Save private measurement checkpoint before expensive matching.
    cache=sqlite3.connect(output/'measurements.sqlite')
    cache.execute('CREATE TABLE characters(font TEXT,character TEXT PRIMARY KEY,region_count INTEGER,area_px INTEGER,canvas_ratio REAL,em_ratio REAL,component_areas_json TEXT,bbox_json TEXT,mask_zlib BLOB)')
    cache.executemany('INSERT INTO characters VALUES (?,?,?,?,?,?,?,?,?)',glyphs.values());cache.commit()
    pairs,correlations=bank.shift_module.translated_pairs(glyphs,set(''.join(shaped)),.95,10)
    (output/'pairs.json').write_text(json.dumps(pairs,ensure_ascii=False),encoding='utf8')
    comparison_words,matches=alternative_matches(competitors,shaped,areas,pairs)
    ambiguous={w for w,m in matches.items() if len(m)>1}
    unique=[w for w in shaped if w not in ambiguous]
    candidates=[w for w in unique if len(set(w))==len(w)]
    needed=set(''.join(candidates))
    render(sorted(needed-metrics.keys()),glyphs,metrics,metadata['browser_version'],require_metrics=True)
    cache.execute('CREATE TABLE stroke_metrics(character TEXT PRIMARY KEY,ink_area INTEGER,implied_area INTEGER,ratio REAL,ink_zlib BLOB,implied_zlib BLOB)')
    cache.executemany('INSERT INTO stroke_metrics VALUES (?,?,?,?,?,?)',metrics.values());cache.commit();cache.close()
    ratios={c:Fraction(r[2],r[1]) for c,r in metrics.items()}
    scores=bank.arithmetic_scores(candidates,ratios)
    selected,used=select_disjoint(candidates,scores,scope_by_length={2:2,3:2,4:4} if args.hsk_combined else None)
    # Assert uniqueness on the complete unfiltered comparison dictionary again.
    _,final_matches=alternative_matches(competitors,selected,areas,pairs)
    if any(len(v)!=1 for v in final_matches.values()):raise ValueError('Nonunique final question')
    summary.update({'bank_type':'hsk-combined' if args.hsk_combined else 'hsk-multi' if args.hsk_multi else 'idiom','source_entries':len(hsk_entries) if is_hsk else len(entries),'idiom_source_sha256':hashlib.sha256(raw).hexdigest(),
        'hsk_sha256':hashlib.sha256(hsk_path.read_bytes()).hexdigest(),'extended_sha256':hashlib.sha256(extended_path.read_bytes()).hexdigest(),
        'font':bank.FONT,'font_sha256':font_hash,'render':metadata['render'],'browser_version':metadata['browser_version'],
        'comparison_words':len(universe),'renderable_comparison_words':len(competitors),
        'unsupported_comparison_words':len(universe)-len(competitors),'unsupported_characters':len(required-supported),
        'excluded_ambiguous_words':len(ambiguous),'unique_answer_words':len(unique),
        'excluded_internal_repetition':len(unique)-len(candidates),'candidates_before_global_deduplication':len(candidates),
        'excluded_global_conflicts':len(candidates)-len(selected),'puzzle_count':len(selected),'distinct_characters':len(used),
        'source_words_by_length':dict(sorted(Counter(map(len,source_words)).items())),
        'puzzles_by_length':dict(sorted(Counter(map(len,selected)).items())),
        'puzzles_by_painted_characters':dict(sorted(Counter(sum(areas[c]>0 for c in w) for w in selected).items())),
        'difficulty_aggregation':'arithmetic-mean-v1; all characters equally weighted, empty paint scores zero',
        'stroke_ratio_min':min((float(scores[w]) for w in selected),default=0),'stroke_ratio_max':max((float(scores[w]) for w in selected),default=0),
        'iou_threshold_exclusive':.95,'manhattan_limit_exclusive_px':10,'close_character_pairs':len(pairs),'translation_correlations':correlations,
        'blank_matching':'blank matches every blank; blank never matches nonempty; no transitive similarity closure',
        'comparison_scope':'all renderable four-Hanzi idioms plus existing HSK and broad words of length >=3; match same length only' if args.hsk_multi else 'all renderable four-Hanzi idioms plus existing HSK and broad four-Hanzi words, before any puzzle filters',
        'character_reuse_scope':'within this bank only, across all selected word lengths, including blank positions',
        'minimum_component_area_px':25,'rectangle_component_minimum_px':25})
    if args.hsk_combined:
        summary.update({'minimum_nonempty_nonrectangle_characters':2,
            'comparison_scope':'all renderable four-Hanzi idioms plus existing HSK and broad words of length 2/3/4; match same length only; before puzzle filters',
            'three_character_words_allow_blank':False,
            'character_reuse_scope':'one shared pool for lengths 2 and 3; separate pool for length 4; includes all positions',
            'distinct_characters_by_scope':{'2+3':len(set(''.join(w for w in selected if len(w) in (2,3)))),'4':len(set(''.join(w for w in selected if len(w)==4)))},
            'distinct_characters_by_length':{n:len(set(''.join(w for w in selected if len(w)==n))) for n in (2,3,4)},
            'editorial_policy_version':policy['version']})
    summary['puzzles_with_single_rectangle_characters']=sum(bool(set(w)&rectangles) for w in selected)
    db=sqlite3.connect(output/'bank.partial.sqlite')
    db.executescript('''
      CREATE TABLE puzzles(id TEXT PRIMARY KEY,ordinal INTEGER UNIQUE,word TEXT UNIQUE,hsk_level TEXT,total_paint_area_px INTEGER,total_ink_area INTEGER,implied_ink_area INTEGER,stroke_ratio REAL);
      CREATE TABLE glyphs(character TEXT PRIMARY KEY,region_count INTEGER,area_px INTEGER,canvas_ratio REAL,em_ratio REAL,component_areas_json TEXT,bbox_json TEXT,mask_zlib BLOB);
      CREATE TABLE stroke_metrics(character TEXT PRIMARY KEY,ink_area INTEGER,implied_area INTEGER,ratio REAL,ink_zlib BLOB,implied_zlib BLOB);
      CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT);
      CREATE TABLE similar_pairs(character_a TEXT,character_b TEXT,intersection_px INTEGER,union_px INTEGER,min_manhattan_px INTEGER,dx INTEGER,dy INTEGER);
      CREATE TABLE excluded_ambiguous(word TEXT PRIMARY KEY);
      CREATE TABLE comparison_words(word TEXT PRIMARY KEY);
      CREATE TABLE excluded_font_characters(character TEXT PRIMARY KEY,reason TEXT);
    ''')
    for ordinal,w in enumerate(selected,1):
        db.execute('INSERT INTO puzzles VALUES (?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),ordinal,w,levels[w] if is_hsk else None,sum(areas[c] for c in w),sum(metrics[c][1] for c in w),sum(metrics[c][2] for c in w),float(scores[w])))
    db.executemany('INSERT INTO glyphs VALUES (?,?,?,?,?,?,?,?)',(glyphs[c][1:] for c in sorted(used)))
    db.executemany('INSERT INTO stroke_metrics VALUES (?,?,?,?,?,?)',(metrics[c] for c in sorted(used)))
    db.executemany('INSERT INTO similar_pairs VALUES (?,?,?,?,?,?,?)',pairs)
    db.executemany('INSERT INTO excluded_ambiguous VALUES (?)',((w,) for w in sorted(ambiguous)))
    db.executemany('INSERT INTO comparison_words VALUES (?)',((w,) for w in comparison_words))
    db.executemany('INSERT INTO excluded_font_characters VALUES (?,?)',[(c,'inconsistent') for c in sorted(font_banned)]+[(c,'missing-font') for c in sorted(font_missing)])
    db.execute('INSERT INTO metadata VALUES (?,?)',('build',json.dumps(summary,ensure_ascii=False)))
    db.commit();db.close();(output/'bank.partial.sqlite').rename(output/'bank.sqlite')
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
