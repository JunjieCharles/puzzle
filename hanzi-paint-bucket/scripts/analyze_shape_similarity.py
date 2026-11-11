"""Position-aware normalized arbitrary-mask IoU, with private same-font reports."""
import argparse
from collections import defaultdict, Counter
from functools import lru_cache
import hashlib
import html
import json
from pathlib import Path
import sqlite3
import zlib

import numpy as np
from scipy import ndimage, sparse
from playwright.sync_api import sync_playwright

from analyze_rectangle_similarity import ROOT, PRIVATE
from analyze_multifont_similarity import font_sources
from build_idiom_bank import alternative_matches, private_path


@lru_cache(maxsize=4096)
def overlap_axis(n, m):
    """Exact normalized overlap lengths of two uniform pixel partitions."""
    rows, cols, values = [], [], []
    i = j = 0
    while i < n and j < m:
        left = max(i*m, j*n)
        right = min((i+1)*m, (j+1)*n)
        if right > left:
            rows.append(i); cols.append(j); values.append((right-left)/(n*m))
        end_a, end_b = (i+1)*m, (j+1)*n
        if end_a <= end_b: i += 1
        if end_b <= end_a: j += 1
    return sparse.csr_matrix((values, (rows, cols)), shape=(n,m))


def shape_signature(mask):
    labels, _ = ndimage.label(mask)
    keep = np.bincount(labels.ravel()) >= 25
    keep[0] = False
    clean = keep[labels]
    ys, xs = np.nonzero(clean)
    if not len(xs):
        return None
    x0,y0,x1,y1 = int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)
    crop = clean[y0:y1,x0:x1]
    return crop, np.array([(x0+x1)/2,(y0+y1)/2])


def normalized_iou(a, b):
    """Continuous area IoU after independently scaling each whole bbox to 1x1."""
    intermediate = overlap_axis(a.shape[0], b.shape[0]) @ b.astype(float)
    integrated = (overlap_axis(a.shape[1], b.shape[1]) @ intermediate.T).T
    intersection = float(integrated[a].sum())
    return intersection / (float(a.mean()+b.mean())-intersection)


def coarse_areas(mask, side=16):
    """Exact area within each grid cell, giving a conservative IoU upper bound."""
    temp = overlap_axis(side, mask.shape[0]) @ mask.astype(float)
    return (overlap_axis(side,mask.shape[1]) @ temp.T).T.ravel()


def find_pairs(shapes, queries, threshold=.90, limit=50):
    chars = sorted(shapes)
    indices = {c:i for i,c in enumerate(chars)}
    centers = np.array([shapes[c][1] for c in chars])
    counts = np.array([ndimage.label(shapes[c][0])[1] for c in chars])
    areas = np.array([shapes[c][0].mean() for c in chars])
    blocks = np.array([coarse_areas(shapes[c][0]) for c in chars])
    pairs, evaluated = [], 0
    for a in sorted(queries & shapes.keys()):
        i = indices[a]
        distances = np.abs(centers-centers[i]).sum(axis=1)
        candidates = np.flatnonzero((counts==counts[i]) & (distances<=limit) & (np.minimum(areas[i],areas)/np.maximum(areas[i],areas)>threshold-1e-12))
        if len(candidates):
            upper = np.minimum(blocks[i],blocks[candidates]).sum(axis=1)
            candidates = candidates[upper/(areas[i]+areas[candidates]-upper)>threshold-1e-12]
        for j in candidates:
            b = chars[j]
            if a==b or (b in queries and b<a): continue
            score = normalized_iou(shapes[a][0],shapes[b][0])
            evaluated += 1
            if score > threshold+1e-12:
                pairs.append((a,b,score,float(distances[j])))
    return pairs,evaluated


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank',type=Path,default=PRIVATE/'hsk-combined-editorial-v23-noto-bank/bank.sqlite')
    parser.add_argument('--cache',type=Path,default=PRIVATE/'multifont-position-v23')
    parser.add_argument('--iou-threshold',type=float,default=.90)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if not .9<=args.iou_threshold<1:parser.error('IoU threshold must be in [0.90,1)')
    output=private_path(args.output or PRIVATE/f'all-shape-same-count-position50-iou{args.iou_threshold*100:g}-v23'); output.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(args.bank.resolve().as_uri()+'?mode=ro',uri=True) as db:
        targets=[r[0] for r in db.execute('SELECT word FROM puzzles ORDER BY ordinal')]
        competitors=[r[0] for r in db.execute('SELECT word FROM comparison_words')]
    queries=set(''.join(targets)); required=set(''.join(competitors))
    hsk={r['word'] for r in json.loads((ROOT.parent/'word-kanji/data/hsk-2025.json').read_text(encoding='utf-8'))['words']}
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True); version=browser.version; browser.close()
    details=defaultdict(dict); summaries=[]
    cache=sqlite3.connect((args.cache/'masks.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    for name,path,face in font_sources():
        raw_meta=cache.execute('SELECT value FROM metadata WHERE font=?',(name,)).fetchone()[0]
        meta=json.loads(raw_meta)
        assert meta=={'sha':hashlib.sha256(path.read_bytes()).hexdigest(),'face':face,'browser':version,'render':'480-400-alpha128-v1'}, 'Stale font cache'
        areas={}; shapes={}
        for c,area,packed in cache.execute('SELECT character,area,mask FROM masks WHERE font=?',(name,)):
            areas[c]=area
            mask=np.unpackbits(np.frombuffer(zlib.decompress(packed),dtype=np.uint8)).reshape(480,480).astype(bool)
            signature=shape_signature(mask)
            if signature is not None: shapes[c]=signature
        supported=set(areas)
        eligible=[w for w in competitors if set(w)<=supported]
        target=[w for w in targets if set(w)<=supported]
        fingerprint=hashlib.sha256((json.dumps(sorted(queries))+raw_meta+json.dumps(sorted(supported))).encode()).hexdigest()
        old=json.loads((args.cache/(name.replace(' ','-')+'-pixel.json')).read_text(encoding='utf-8'))
        assert old['fingerprint']==fingerprint,'Stale pixel pair cache'
        counts={c:ndimage.label(shapes[c][0])[1] if c in shapes else 0 for c in areas}
        old['pairs']=[r for r in old['pairs'] if counts[r[0]]==counts[r[1]]]
        pairs,evaluated=find_pairs(shapes,queries,args.iou_threshold)
        (output/(name.replace(' ','-')+'-shape.json')).write_text(json.dumps(pairs,ensure_ascii=False),encoding='utf-8')
        pixel={tuple(sorted(r[:2])) for r in old['pairs']}
        shape_map={tuple(sorted(r[:2])):r[2:] for r in pairs}
        words,matches=alternative_matches(eligible,target,areas,old['pairs']+[r[:2] for r in pairs])
        _,shape_matches=alternative_matches(eligible,target,areas,[r[:2] for r in pairs])
        affected=0
        for word,ids in matches.items():
            alternatives=[words[i] for i in ids if words[i]!=word]
            if alternatives: affected+=1
            for alt in alternatives:
                changes=[]
                for a,b in zip(word,alt):
                    if a==b:continue
                    pair=tuple(sorted((a,b)))
                    geometry=shape_map.get(pair)
                    changes.append({'a':a,'b':b,'shape_iou':geometry[0] if geometry else None,
                                    'center_l1':geometry[1] if geometry else None,'pixel_match':pair in pixel,
                                    'blank_match':areas[a]==areas[b]==0})
                details[word].setdefault(alt,[]).append({'font':name,'changes':changes})
        row={'font':name,'affected':affected,'shape_only_affected':sum(len(v)>1 for v in shape_matches.values()),
             'exact_comparisons':evaluated,'shape_pairs':len(pairs),'missing_characters':len(required-supported),'unverifiable_questions':len(targets)-len(target)}
        summaries.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    cache.close()
    previous=json.loads((args.cache/'details.json').read_text(encoding='utf-8'))
    prior40=set(previous['rect95-center40']);prior50=set(previous['rect95-center50'])
    summary={'questions':len(targets),'comparison_words':len(competitors),'iou_exclusive':args.iou_threshold,'center_l1_inclusive':50,'equal_component_count_required':True,
             'affected':len(details),'by_length':dict(Counter(map(len,details))),
             'with_hsk_alternative':sum(any(a in hsk for a in alts) for alts in details.values()),
             'remaining_without_refill':len(targets)-len(details),'added_vs_rectangle95_center40':len(set(details)-prior40),
             'removed_vs_rectangle95_center40':len(prior40-set(details)),
             'added_vs_rectangle95_center50':len(set(details)-prior50),'removed_vs_rectangle95_center50':len(prior50-set(details)),
             'per_font':summaries}
    baseline_path=PRIVATE/'all-shape-same-count-position50-iou90-v23/details.json'
    comparison=None
    if args.iou_threshold>.9 and baseline_path.exists():
        baseline=json.loads(baseline_path.read_text(encoding='utf-8'))
        comparison={'still_affected':[w for w in targets if w in details],
                    'no_longer_affected':[w for w in targets if w in baseline and w not in details],
                    'newly_affected':[w for w in targets if w in details and w not in baseline]}
        summary['comparison_to_iou90']={key:len(value) for key,value in comparison.items()}
        (output/'comparison-to-iou90.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'details.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    rows=[]
    for word in sorted(details,key=lambda w:(not any(a in hsk for a in details[w]),targets.index(w))):
        choices=[]
        for alt,evidence in details[word].items():
            lines=[]
            for e in evidence:
                parts=[]
                for c in e['changes']:
                    rules=[]
                    if c['shape_iou'] is not None:rules.append(f"图形IoU {c['shape_iou']:.3%}，中心距离 {c['center_l1']:g}px")
                    if c['pixel_match']:rules.append('原像素规则')
                    if c['blank_match']:rules.append('空白匹配')
                    parts.append(html.escape(c['a']+'↔'+c['b'])+'：'+' / '.join(rules))
                lines.append(html.escape(e['font'])+' — '+'；'.join(parts))
            choices.append('<strong>'+html.escape(alt)+'</strong>'+('【HSK】' if alt in hsk else '【扩展词库】')+'<details><summary>命中字形与分数</summary>'+'<br>'.join(lines)+'</details>')
        rows.append('<tr><td>'+html.escape(word)+('</td><td>新增' if word not in prior40 else '</td><td>此前已命中')+'</td><td>'+'<br>'.join(choices)+'</td></tr>')
    document='<!doctype html><meta charset="utf-8"><title>任意图形多解试验</title><style>body{font:16px/1.7 sans-serif;max-width:1250px;margin:30px auto}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:10px;text-align:left}details{font-size:14px;color:#456}</style>'
    document+=f'<h1>任意图形：同块数，中心≤50px，IoU&gt;{args.iou_threshold:.0%}</h1><p>当前212题中受影响{len(details)}题；其中{summary["with_hsk_alternative"]}题存在HSK替代词。六字体分别比较整词，任一字体完整命中即多解。保留原像素规则。</p><p>忽略面积小于25px的连通块，有效连通块数必须相同；整组实际图形包围盒横纵分别归一化，保留孔洞与间隙，不要求矩形。使用连续像素单元面积精确计算IoU。新增标记相对于上一轮矩形95%／40px／六字体的20题。</p><h2>仍受影响的题目</h2><table><tr><th>当前题目</th><th>与矩形规则比较</th><th>替代词与证据（HSK优先）</th></tr>'+''.join(rows)+'</table>'
    if comparison is not None:
        document+=f'<h2>相较90%不再命中的题目（{len(comparison["no_longer_affected"])}题）</h2><p>'+html.escape('、'.join(comparison['no_longer_affected']))+'</p>'
    (output/'report.html').write_text(document,encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
