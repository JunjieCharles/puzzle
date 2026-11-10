"""Build a private HSK bank with globally disjoint characters, hardest first."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid
import zlib
from fractions import Fraction
import importlib.util
import math

import numpy as np
from scipy.spatial.distance import cdist
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
FONT = 'HarmonyOS Sans SC'

policy_spec=importlib.util.spec_from_file_location('paint_vocabulary_policy',ROOT/'scripts/vocabulary_policy.py')
policy_module=importlib.util.module_from_spec(policy_spec);policy_spec.loader.exec_module(policy_module)
shift_spec=importlib.util.spec_from_file_location('paint_shift_similarity',ROOT/'scripts/analyze_shift_similarity.py')
shift_module=importlib.util.module_from_spec(shift_spec);shift_spec.loader.exec_module(shift_module)


def ambiguous_words(words, similar_pairs, targets=None):
    """Word alternatives require a match at every position, not just one letter."""
    words = sorted(set(words))
    word_set = set(words)
    neighbours = {c:{c} for c in set(''.join(words))}
    for a,b in similar_pairs:
        if a in neighbours and b in neighbours:
            neighbours[a].add(b); neighbours[b].add(a)
    index = {}
    for i,w in enumerate(words):
        for pos,c in enumerate(w):
            index.setdefault((len(w),pos,c),set()).add(i)
    result = set()
    for w in words if targets is None else targets:
        if w not in word_set:
            raise ValueError('Query word must be in ambiguity vocabulary')
        matches = None
        for pos,c in enumerate(w):
            ids = set().union(*(index.get((len(w),pos,other),set()) for other in neighbours[c]))
            matches = ids if matches is None else matches & ids
            if len(matches)<=1:
                break
        if len(matches)>1:
            result.add(w)
    return result


def query_shape_pairs(glyphs, query_chars, tolerance):
    """Compare HSK query glyphs to all paintable extended glyphs without re-rendering."""
    chars = sorted(c for c,r in glyphs.items() if r[3]>0)
    packed = np.array([np.frombuffer(zlib.decompress(glyphs[c][-1]),dtype=np.uint8) for c in chars])
    areas = np.array([glyphs[c][3] for c in chars],dtype=np.int64)
    blocks = np.array([np.unpackbits(row).reshape(24,20,24,20).sum(axis=(1,3)).ravel() for row in packed],dtype=np.float64)
    queries = [i for i,c in enumerate(chars) if c in query_chars]
    query_set = set(queries)
    popcount = np.array([i.bit_count() for i in range(256)],dtype=np.uint8)
    pairs=[]
    for start in range(0,len(queries),64):
        batch=queries[start:start+64]
        lower_xor=cdist(blocks[batch],blocks,metric='cityblock')
        sums=areas[batch,None]+areas[None,:]
        bound=2*lower_xor/(sums+lower_xor)
        for row,j in np.argwhere(bound<=tolerance+1e-12):
            i=batch[row]
            if i==j or (j in query_set and j<i):
                continue
            xor=int(popcount[np.bitwise_xor(packed[i],packed[j])].sum())
            distance=2*xor/(int(areas[i]+areas[j])+xor)
            if distance<=tolerance+1e-12:
                pairs.append((chars[i],chars[j],distance))
    return pairs


def is_single_solid_rectangle(mask, font_size=400):
    """Ignore regions below 25 px for this filter only, then inspect the box."""
    labels, count = ndimage.label(mask)
    sizes = np.bincount(labels.ravel(), minlength=count+1)
    keep = sizes >= 25
    keep[0] = False
    mask = keep[labels]
    ys,xs=np.nonzero(mask)
    if not len(xs):
        return False
    box=mask[ys.min():ys.max()+1,xs.min():xs.max()+1].copy()
    if box.all():
        return True
    if len(xs)/box.size < .995:
        return False
    # Four-connected foreground must be a single region; no enclosed white holes.
    if ndimage.label(box)[1]!=1 or not np.array_equal(ndimage.binary_fill_holes(box),box):
        return False
    band=max(1,int(np.ceil(font_size*.005)))
    if min(box.shape)<=2*band:
        return False
    return bool(box[band:-band,band:-band].all())


def arithmetic_scores(words, ratios):
    """Equal character weights, with exact rational comparisons."""
    return {w:sum((ratios[c] for c in w),Fraction(0))/len(w) for w in words}


def geometric_scores(words, ratios):
    """Exact comparable powers of geometric means, including mixed word lengths."""
    power = math.lcm(*(len(w) for w in words)) if words else 1
    return {w: math.prod(ratios[c] for c in w) ** (power // len(w)) for w in words}, power


def select_words(words, areas, ambiguous=(), excluded_chars=(), scores=None, excluded_words=(), component_areas=None, word_length=None):
    words = sorted(set(w for w in words if len(w) >= 2 and (word_length is None or len(w)==word_length)))
    paintable = [w for w in words if all(areas.get(c, 0) > 0 for c in w)]
    visible = paintable if component_areas is None else [w for w in paintable if all(max(component_areas.get(c,()),default=0)>=25 for c in w)]
    shaped = [w for w in visible if not set(w).intersection(excluded_chars)]
    editorial = [w for w in shaped if w not in excluded_words]
    unique = [w for w in editorial if w not in ambiguous]
    candidates = [w for w in unique if len(set(w)) == len(w)]
    score=(lambda w:scores[w]) if scores is not None else (lambda w:sum(areas[c] for c in w))
    used, selected = set(), []
    for word in sorted(candidates, key=lambda w: (score(w), w)):
        if used.isdisjoint(word):
            selected.append(word)
            used.update(word)
    selected.sort(key=lambda w: (-score(w), w))
    return selected, {'hsk_multi_character_words': len(words),
        'all_characters_paintable': len(paintable),
        'excluded_tiny_region_words':len(paintable)-len(visible),
        'after_minimum_region_filter':len(visible),
        'excluded_single_rectangle_words':len(visible)-len(shaped),
        'after_shape_filter':len(shaped),
        'excluded_editorial_words':len(shaped)-len(editorial),
        'after_editorial_filter':len(editorial),
        'excluded_ambiguous_words':len(editorial)-len(unique),
        'unique_answer_words':len(unique),
        'excluded_internal_repetition': len(unique)-len(candidates),
        'candidates_before_global_deduplication': len(candidates),
        'excluded_global_conflicts': len(candidates)-len(selected),
        'puzzle_count': len(selected), 'distinct_characters': len(used),
        'puzzles_by_length': dict(sorted(Counter(map(len,selected)).items()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lexicon',type=Path,default=REPO/'word-kanji/data/hsk-2025.json')
    parser.add_argument('--analysis',type=Path,default=REPO.parent/'puzzle-private/hanzi-paint-bucket/extended-analysis/analysis.sqlite')
    parser.add_argument('--extended-lexicon',type=Path,default=REPO/'word-kanji/public/endless-lexicon.json')
    parser.add_argument('--iou-threshold',type=float,default=.95)
    parser.add_argument('--max-manhattan',type=int,default=10)
    parser.add_argument('--stroke-analysis',type=Path,default=REPO.parent/'puzzle-private/hanzi-paint-bucket/stroke-analysis/metrics.sqlite')
    parser.add_argument('--policy',type=Path,default=REPO.parent/'puzzle-private/hanzi-paint-bucket/vocabulary-policy.json')
    parser.add_argument('--output',type=Path,default=REPO.parent/'puzzle-private/hanzi-paint-bucket/hsk-bank-demonstratives-questions-v2')
    args = parser.parse_args()
    if not .9 <= args.iou_threshold < 1 or not 1 <= args.max_manhattan <= 480:
        parser.error('Use IoU threshold in [0.9,1) and Manhattan limit in [1,480]')
    policy_path=args.policy.resolve()
    if policy_path==REPO or REPO in policy_path.parents:
        parser.error('Concrete editorial policy must remain outside repository')
    policy=json.loads(policy_path.read_text(encoding='utf-8'))
    output = args.output.resolve()
    if output == REPO or REPO in output.parents:
        parser.error('Private bank must remain outside repository')
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):
        parser.error('Use a new empty output directory')
    source = sqlite3.connect(args.analysis.resolve().as_uri()+'?mode=ro',uri=True)
    metadata = json.loads(source.execute("SELECT value_json FROM metadata WHERE key='summary'").fetchone()[0])
    lexicon_hash = hashlib.sha256(args.lexicon.read_bytes()).hexdigest()
    font_hash = hashlib.sha256((ROOT/'public/fonts/HarmonyOS_Sans_SC_Thin.ttf').read_bytes()).hexdigest()
    if metadata['lexicon_sha256'] != lexicon_hash or metadata['font_sources'][FONT]['sha256'] != font_hash:
        raise ValueError('Analysis font or HSK snapshot does not match current sources')
    if metadata['render'] != {'canvas':480,'font_size':400,'alpha_threshold':128,'connectivity':4}:
        raise ValueError('Unexpected rendering parameters')
    extended_hash = hashlib.sha256(args.extended_lexicon.read_bytes()).hexdigest()
    if metadata.get('scope') != 'extended' or metadata.get('extended_lexicon_sha256') != extended_hash:
        raise ValueError('Analysis does not match requested extended vocabulary')
    entries = json.loads(args.lexicon.read_text(encoding='utf-8'))['words']
    editorial=policy_module.editorial_exclusions(entries,policy)
    levels = {r['word']:r['level'] for r in entries}
    glyphs = {r[1]:r for r in source.execute('SELECT * FROM characters WHERE font=?',(FONT,))}
    missing = {r[0] for r in source.execute('SELECT character FROM missing_glyphs WHERE font=?',(FONT,))}
    extended = json.loads(args.extended_lexicon.read_text(encoding='utf-8'))
    universe = sorted(w for w in set(extended['broad']) | set(levels) if len(w)>=2)
    required = set(''.join(universe))
    if required - glyphs.keys() - missing:
        raise ValueError('Analysis does not cover requested vocabulary')
    areas = {c:r[3] for c,r in glyphs.items()}
    paintable = [w for w in levels if len(w)>=2 and all(areas.get(c,0)>0 for c in w)]
    competitors = [w for w in universe if all(areas.get(c,0)>0 for c in w)]
    print('Comparing HSK two-character glyphs using global translation maxima...',flush=True)
    targets=[w for w in paintable if len(w)==2]
    pairs,correlations = shift_module.translated_pairs(glyphs,set(''.join(targets)),args.iou_threshold,args.max_manhattan)
    ambiguous = ambiguous_words(competitors,[(r[0],r[1]) for r in pairs],targets)
    rectangles = {c for c,r in glyphs.items() if r[3]>0 and is_single_solid_rectangle(
        np.unpackbits(np.frombuffer(zlib.decompress(r[-1]),dtype=np.uint8)).reshape(480,480))}
    stroke_db=sqlite3.connect(args.stroke_analysis.resolve().as_uri()+'?mode=ro',uri=True)
    stroke_meta=json.loads(stroke_db.execute("SELECT value_json FROM metadata WHERE key='build'").fetchone()[0])
    if (stroke_meta['font_sha256']!=font_hash or stroke_meta['hsk_sha256']!=lexicon_hash
        or stroke_meta['render']!=metadata['render'] or stroke_meta['browser_version']!=metadata['browser_version']):
        raise ValueError('Stroke metrics do not match current paint analysis')
    metrics={r[0]:r for r in stroke_db.execute('SELECT * FROM characters')}
    stroke_db.close()
    if set(''.join(paintable))-metrics.keys():raise ValueError('Missing stroke measurements')
    scores = arithmetic_scores(paintable, {c:Fraction(r[2],r[1]) for c,r in metrics.items()})
    displayed_scores={w:float(score) for w,score in scores.items()}
    component_areas={c:json.loads(r[6]) for c,r in glyphs.items()}
    selected, summary = select_words(levels,areas,ambiguous,rectangles,scores,editorial,component_areas,word_length=2)
    summary['hsk_two_character_words']=summary.pop('hsk_multi_character_words')
    summary['question_word_length']=2
    summary.update({'font':FONT,'font_sha256':font_hash,'hsk_sha256':lexicon_hash,
        'render':metadata['render'],'minimum_component_area_px':25,
        'tiny_region_chars_in_hsk_paintable_words':sum(max(component_areas[c],default=0)<25 for c in set(''.join(paintable))),
        'selection':'ascending arithmetic mean of character implied-ink / ink ratios, accept if all characters unused; Unicode lexical tie-break',
        'display_order':'descending arithmetic mean of character implied-ink / ink ratios; Unicode lexical tie-break',
        'difficulty_aggregation':'arithmetic-mean-v1',
        'difficulty_method':{**stroke_meta,'word_aggregation':'arithmetic mean of per-character implied ink / all ink'},
        'stroke_ratio_min':min((displayed_scores[w] for w in selected),default=0),
        'stroke_ratio_max':max((displayed_scores[w] for w in selected),default=0),
        'area_total_min':min((sum(areas[c] for c in w) for w in selected),default=0),
        'area_total_max':max((sum(areas[c] for c in w) for w in selected),default=0),
        'levels':dict(sorted(Counter(levels[w] for w in selected).items())),
        'similarity_filter_applied':True,'iou_threshold_exclusive':args.iou_threshold,
        'manhattan_limit_exclusive_px':args.max_manhattan,'translation_correlations':correlations,
        'ambiguity_vocabulary':'extended broad union HSK; words of length >=2; includes internal repetition and words not selected for bank',
        'extended_sha256':extended_hash,'ambiguity_universe_words':len(universe),
        'paintable_competitor_words':len(competitors),
        'missing_glyphs_in_universe':len(required & missing),
        'universe_words_with_missing_glyphs':sum(bool(set(w)&missing) for w in universe),
        'compared_query_characters':len(set(''.join(targets))),
        'close_character_pairs':len(pairs),
        'shape_exclusion':'ignore components below 25 pixels for rectangle classification only; one remaining 4-connected region; bounding-box fill >=99.5%; no enclosed holes; missing pixels confined to outer ceil(font_size*0.005) band',
        'rectangle_component_minimum_px':25,
        'rectangle_fill_minimum':.995,'rectangle_edge_band_px':2,
        'single_rectangle_chars_in_hsk_paintable_words':len(rectangles & set(''.join(paintable))),
        'ambiguous_words_before_shape_filter':len(ambiguous),
        'ambiguity_position_policy':'global integer translation maximum IoU; minimum Manhattan distance among all global maximizers; no clipping; independent per character'})
    summary.update({'editorial_policy_version':policy['version'],
        'editorial_policy_sha256':hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        'editorial_excluded_hsk_multi_words':sum(w in editorial for w in levels if len(w)>=2),
        'editorial_excluded_paintable_words':sum(w in editorial for w in paintable),
        'editorial_validation_vocabulary_unchanged':True})
    db = sqlite3.connect(output/'bank.partial.sqlite')
    db.executescript('''
      CREATE TABLE puzzles(id TEXT PRIMARY KEY, ordinal INTEGER UNIQUE, word TEXT UNIQUE,
        hsk_level TEXT, total_paint_area_px INTEGER, total_ink_area INTEGER, implied_ink_area INTEGER, stroke_ratio REAL);
      CREATE TABLE glyphs(character TEXT PRIMARY KEY, region_count INTEGER, area_px INTEGER,
        canvas_ratio REAL, em_ratio REAL, component_areas_json TEXT, bbox_json TEXT, mask_zlib BLOB);
      CREATE TABLE metadata(key TEXT PRIMARY KEY,value_json TEXT);
      CREATE TABLE similar_pairs(character_a TEXT,character_b TEXT,intersection_px INTEGER,union_px INTEGER,min_manhattan_px INTEGER,dx INTEGER,dy INTEGER);
      CREATE TABLE excluded_ambiguous(word TEXT PRIMARY KEY);
      CREATE TABLE excluded_single_rectangle(character TEXT PRIMARY KEY);
      CREATE TABLE stroke_metrics(character TEXT PRIMARY KEY,ink_area INTEGER,implied_area INTEGER,ratio REAL,ink_zlib BLOB,implied_zlib BLOB);
      CREATE TABLE editorial_exclusions(word TEXT PRIMARY KEY,reason TEXT);
    ''')
    used = set()
    for ordinal,word in enumerate(selected,1):
        assert len(word)==len(set(word)) and used.isdisjoint(word)
        used.update(word)
        db.execute('INSERT INTO puzzles VALUES (?,?,?,?,?,?,?,?)',
            (str(uuid.uuid4()),ordinal,word,levels[word],sum(areas[c] for c in word),
             sum(metrics[c][1] for c in word),sum(metrics[c][2] for c in word),displayed_scores[word]))
        for c in word:
            db.execute('INSERT INTO glyphs VALUES (?,?,?,?,?,?,?,?)',glyphs[c][1:])
            db.execute('INSERT INTO stroke_metrics VALUES (?,?,?,?,?,?)',metrics[c])
    db.execute('INSERT INTO metadata VALUES (?,?)',('build',json.dumps(summary,ensure_ascii=False)))
    db.executemany('INSERT INTO similar_pairs VALUES (?,?,?,?,?,?,?)',pairs)
    db.executemany('INSERT INTO excluded_ambiguous VALUES (?)',((w,) for w in sorted(ambiguous)))
    db.executemany('INSERT INTO excluded_single_rectangle VALUES (?)',((c,) for c in sorted(rectangles)))
    db.executemany('INSERT INTO editorial_exclusions VALUES (?,?)',sorted(editorial.items()))
    db.execute('INSERT INTO metadata VALUES (?,?)',('editorial_policy',json.dumps(policy,ensure_ascii=False)))
    db.commit(); db.close(); source.close()
    (output/'bank.partial.sqlite').rename(output/'bank.sqlite')
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
