"""Subset only interface source text, never puzzle/answer data, under Source Han Sans OFL."""
import argparse
import os
from pathlib import Path
from fontTools import subset
from fontTools.ttLib import TTFont

ROOT=Path(__file__).resolve().parents[1]
SOURCES=('index.html','game.mjs','state.mjs','load-resource.mjs','decrypt.mjs')


def build(source_dir):
    public=ROOT/'public'
    text=''.join((public/name).read_text(encoding='utf8') for name in SOURCES)
    points=set(range(32,127))|{ord(c) for c in text}
    for source,target in [('SourceHanSansCN-Light.otf','PaintBucketUI-Light.woff2'),
                          ('SourceHanSansCN-Medium.otf','PaintBucketUI-Medium.woff2')]:
        with TTFont(source_dir/source) as font:
            options=subset.Options();options.flavor='woff2'
            options.name_IDs=['*'];options.name_legacy=True;options.name_languages=['*']
            job=subset.Subsetter(options=options);job.populate(unicodes=points)
            job.subset(font)
            # OFL reserves "Source"; use distinct names for modified UI subsets.
            style='Light' if 'Light' in source else 'Medium'
            names={1:'Paint Bucket UI',2:style,3:f'PaintBucketUI-{style}-2.005',
                   4:f'Paint Bucket UI {style}',6:f'PaintBucketUI-{style}',
                   16:'Paint Bucket UI',17:style,18:f'Paint Bucket UI {style}',
                   21:'Paint Bucket UI',22:style}
            for record in font['name'].names:
                if record.nameID in names:
                    record.string=names[record.nameID].encode(record.getEncoding())
            if 'CFF ' in font:
                cff=font['CFF '].cff;cff.fontNames=[f'PaintBucketUI-{style}']
                top=cff.topDictIndex[0];top.FamilyName='Paint Bucket UI';top.FullName=f'Paint Bucket UI {style}'
            font.flavor='woff2';font.save(public/'fonts'/target)
    print('Built interface-only Source Han Sans subsets from static UI sources.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',type=Path,default=ROOT.parent.parent/'puzzle-private/hanzi-paint-bucket/sourcehan-weight-comparison/fonts')
    build(parser.parse_args().source_dir)
