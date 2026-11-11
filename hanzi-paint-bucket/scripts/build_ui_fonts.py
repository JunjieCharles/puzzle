"""Subset only interface source text, never puzzle/answer data, under Noto OFL."""
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
    for source,target in [('NotoSansSC-6.ttf','NotoSansSC-UI-Regular.woff2'),
                          ('NotoSansSCMedium-4.ttf','NotoSansSC-UI-Medium.woff2')]:
        with TTFont(source_dir/source) as font:
            options=subset.Options();options.flavor='woff2'
            options.name_IDs=['*'];options.name_legacy=True;options.name_languages=['*']
            job=subset.Subsetter(options=options);job.populate(unicodes=points)
            job.subset(font);font.flavor='woff2';font.save(public/'fonts'/target)
    print('Built interface-only Noto subsets from static UI sources.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',type=Path,default=Path(os.environ.get('LOCALAPPDATA',''))/'Microsoft/Windows/Fonts')
    build(parser.parse_args().source_dir)
