"""Private translated-mask sensitivity analysis; public output is aggregate only."""
import argparse
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import sqlite3
import zlib

import numpy as np
from scipy import ndimage, signal

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


def best_translation(a, b):
    """Global integer translation, no clipping; ties prefer minimum L1 distance."""
    def crop(mask):
        y,x = np.nonzero(mask)
        if not len(x):
            raise ValueError('Nonempty masks required')
        return mask[y.min():y.max()+1,x.min():x.max()+1], (int(y.min()),int(x.min()))
    aa,ao = crop(a)
    bb,bo = crop(b)
    # Binary cross-correlation is the exact intersection count up to FFT rounding.
    overlap = np.rint(signal.fftconvolve(aa.astype(float),bb[::-1,::-1].astype(float),mode='full')).astype(np.int64)
    intersection = int(overlap.max())
    ys,xs = np.nonzero(overlap == intersection)
    dy = ys-(bb.shape[0]-1)+ao[0]-bo[0]
    dx = xs-(bb.shape[1]-1)+ao[1]-bo[1]
    distances = np.abs(dy)+np.abs(dx)
    k = int(np.argmin(distances))
    union = int(a.sum()+b.sum())-intersection
    return intersection, union, int(distances[k]), int(dx[k]), int(dy[k])


def translated_pairs(glyphs, query_chars, iou_floor=.9, distance_limit=20):
    """Safe local-overlap upper bound, then global correlation for survivors."""
    chars = sorted(c for c,r in glyphs.items() if r[3]>0)
    masks = [np.unpackbits(np.frombuffer(zlib.decompress(glyphs[c][-1]),dtype=np.uint8)).reshape(480,480).astype(bool) for c in chars]
    areas = np.array([m.sum() for m in masks],dtype=np.int64)
    blocks = np.array([m.reshape(24,20,24,20).sum(axis=(1,3)).ravel() for m in masks])
    # Any shift with L1 < limit lies inside this square dilation. Counts in
    # each fixed block bound all intersections, including shifts near edges.
    radius = int(np.ceil(distance_limit))-1
    expanded = np.array([ndimage.maximum_filter(m,size=2*radius+1,mode='constant').reshape(24,20,24,20).sum(axis=(1,3)).ravel() for m in masks])
    queries = {i for i,c in enumerate(chars) if c in query_chars}
    pairs=[]
    verified=0
    for step,i in enumerate(sorted(queries)):
        candidates=np.flatnonzero(np.minimum(areas[i],areas)/np.maximum(areas[i],areas)>iou_floor)
        candidates=np.array([int(j) for j in candidates if j!=i and not (j in queries and j<i)],dtype=int)
        if len(candidates):
            upper=np.minimum(blocks[i],expanded[candidates]).sum(axis=1)
            candidates=candidates[upper/(areas[i]+areas[candidates]-upper)>iou_floor]
        for j in candidates:
            verified+=1
            inter,union,distance,dx,dy=best_translation(masks[i],masks[j])
            if inter/union>iou_floor and distance<distance_limit:
                pairs.append((chars[i],chars[j],inter,union,distance,dx,dy))
        if (step+1)%200==0:
            print(f'Queries {step+1}/{len(queries)}; correlations {verified}; qualifying pairs {len(pairs)}',flush=True)
    return pairs,verified


def main():
    spec = importlib.util.spec_from_file_location('shift_bank', ROOT/'scripts/build_hsk_bank.py')
    bank = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bank)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=REPO.parent/'puzzle-private/hanzi-paint-bucket/shift-analysis')
    args=parser.parse_args()
    output=args.output.resolve()
    if output==REPO or REPO in output.parents:
        parser.error('Private analysis must remain outside repository')
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):parser.error('Use an empty output directory')
    private=REPO.parent/'puzzle-private/hanzi-paint-bucket'
    with sqlite3.connect(private/'extended-analysis/analysis.sqlite') as db:
        glyphs={r[1]:r for r in db.execute('SELECT * FROM characters WHERE font=?',(bank.FONT,))}
    entries=json.loads((REPO/'word-kanji/data/hsk-2025.json').read_text(encoding='utf8'))['words']
    words={r['word'] for r in entries if len(r['word'])==2}
    areas={c:r[3] for c,r in glyphs.items()}
    paintable={w for w in words if all(areas.get(c,0)>0 for c in w)}
    broad=json.loads((REPO/'word-kanji/public/endless-lexicon.json').read_text(encoding='utf8'))['broad']
    competitors=sorted(w for w in set(broad)|{r['word'] for r in entries} if len(w)==2 and all(areas.get(c,0)>0 for c in w))
    pairs,verified=translated_pairs(glyphs,set(''.join(paintable)))
    # Private reusable evidence, never an output in the repository.
    (output/'pairs.json').write_text(json.dumps(pairs,ensure_ascii=False),encoding='utf8')
    with sqlite3.connect(private/'stroke-analysis/metrics.sqlite') as db:
        ratios={r[0]:Fraction(r[2],r[1]) for r in db.execute('SELECT * FROM characters')}
    scores,_=bank.geometric_scores(paintable,ratios)
    rectangles={c for c,r in glyphs.items() if r[3]>0 and bank.is_single_solid_rectangle(np.unpackbits(np.frombuffer(zlib.decompress(r[-1]),dtype=np.uint8)).reshape(480,480))}
    policy=json.loads((private/'vocabulary-policy.json').read_text(encoding='utf8'))
    editorial=bank.policy_module.editorial_exclusions(entries,policy)
    components={c:json.loads(r[6]) for c,r in glyphs.items()}
    with sqlite3.connect(private/'hsk-bank-geometric-two-clean/bank.sqlite') as db:
        baseline={r[0] for r in db.execute('SELECT word FROM puzzles')}
    summary={'translation':'global integer maximum IoU; minimum Manhattan among global maximizers; no clipping, rotation or scaling',
             'threshold_comparison':'strict > IoU and strict < distance; pixels on 480 canvas / 400 font',
             'correlations':verified,'baseline_puzzles':len(baseline),'settings':[]}
    for threshold in [.90,.95,.98]:
        for limit in [5,10,20]:
            matched=[(a,b) for a,b,inter,union,distance,dx,dy in pairs if Fraction(inter,union)>Fraction(str(threshold)) and distance<limit]
            ambiguous=bank.ambiguous_words(competitors,matched,paintable)
            selected,stats=bank.select_words(words,areas,ambiguous,rectangles,scores,editorial,components,word_length=2)
            summary['settings'].append({'iou_gt':threshold,'manhattan_lt':limit,'similar_character_pairs':len(matched),
                'ambiguous_paintable_words':len(ambiguous),'excluded_ambiguous_words':stats['excluded_ambiguous_words'],
                'puzzle_count':len(selected),'removed_from_baseline':len(baseline-set(selected)),
                'added_to_baseline':len(set(selected)-baseline)})
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()
