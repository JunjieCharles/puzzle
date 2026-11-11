"""Production same-font whole-word ambiguity filter; private data only."""
from collections import defaultdict
import hashlib
import json
import sqlite3
import zlib

import numpy as np
from scipy import ndimage
from fontTools.ttLib import TTFont

from analyze_shape_similarity import shape_signature, find_pairs
from game_font import FAMILY
from analyze_multifont_similarity import font_sources
from analyze_shift_similarity import translated_pairs
from build_idiom_bank import alternative_matches, private_path


def match_font(competitors, targets, areas, pixel_pairs, shape_pairs, counts):
    """Match a whole word in one font; never union character graphs across fonts."""
    pairs=[r[:2] for r in pixel_pairs if counts[r[0]]==counts[r[1]]]
    pairs.extend(r[:2] for r in shape_pairs if counts[r[0]]==counts[r[1]])
    words,ids=alternative_matches(competitors,targets,areas,pairs)
    return {word:{words[i] for i in indices} for word,indices in ids.items()}


def check_words(competitors, targets, cache_directory, output, browser_version, noto_pairs):
    cache_directory=private_path(cache_directory);output=private_path(output)
    required=set(''.join(competitors));queries=set(''.join(targets))
    combined={w:{w} for w in targets};evidence=defaultdict(dict);statistics=[];manifests={}
    with sqlite3.connect((cache_directory/'masks.sqlite').as_uri()+'?mode=ro',uri=True) as cache:
        for name,path,face in font_sources('sourcehan'):
            stored=cache.execute('SELECT value FROM metadata WHERE font=?',(name,)).fetchone()
            expected={'sha':hashlib.sha256(path.read_bytes()).hexdigest(),'face':face,'browser':browser_version,'render':'480-400-alpha128-v1'}
            if stored is None or json.loads(stored[0])!=expected:
                raise ValueError('Rebuild six-font ambiguity cache: fingerprint differs')
            with TTFont(path,fontNumber=face if face is not None else -1) as font:
                supported=required & {chr(c) for c in font.getBestCmap()}
            glyphs={c:(name,c,0,area,packed) for c,area,packed in cache.execute('SELECT character,area,mask FROM masks WHERE font=?',(name,)) if c in supported}
            if glyphs.keys()!=supported:raise ValueError('Rebuild six-font ambiguity cache: missing measurements')
            shapes={};counts={};areas={c:r[3] for c,r in glyphs.items()}
            for c,r in glyphs.items():
                mask=np.unpackbits(np.frombuffer(zlib.decompress(r[-1]),dtype=np.uint8)).reshape(480,480).astype(bool)
                signature=shape_signature(mask)
                counts[c]=ndimage.label(signature[0])[1] if signature else 0
                if signature is not None:shapes[c]=signature
            if any(not set(w)<=supported for w in targets):
                raise ValueError('A candidate cannot be verified in all six fonts')
            shape_pairs,evaluated=find_pairs(shapes,queries,.95,50)
            if name==FAMILY:pixel_pairs=noto_pairs
            else:pixel_pairs,_=translated_pairs(glyphs,queries,.95,10)
            matches=match_font([w for w in competitors if set(w)<=supported],targets,areas,pixel_pairs,shape_pairs,counts)
            for word,alternatives in matches.items():
                combined[word].update(alternatives)
                for alternative in alternatives-{word}:
                    evidence[word].setdefault(alternative,[]).append(name)
            (output/(name.replace(' ','-')+'-ambiguity-pairs.json')).write_text(json.dumps({'pixel':pixel_pairs,'shape':shape_pairs},ensure_ascii=False),encoding='utf-8')
            row={'font':name,'affected_candidates':sum(len(v)>1 for v in matches.values()),'missing_comparison_characters':len(required-supported),'shape_pairs':len(shape_pairs),'exact_shape_comparisons':evaluated}
            statistics.append(row);manifests[name]=expected
            print(json.dumps(row,ensure_ascii=False),flush=True)
    (output/'ambiguity-matches.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    return combined,{'multifont_ambiguity_applied':True,'ambiguity_method':'same-font-whole-word-shape95-center50-or-pixel95-shift10-equal-components-v1',
                     'shape_iou_threshold_exclusive':.95,'shape_center_l1_limit_inclusive_px':50,'similarity_equal_effective_components':True,
                     'ambiguity_font_results':statistics,'ambiguity_font_fingerprints':manifests}
