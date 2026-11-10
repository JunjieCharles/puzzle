"""Fetch a pinned generic idiom dictionary into the private source directory."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

REPO=Path(__file__).resolve().parents[2]
COMMIT='fe6d6c2e8baa82187f4c96bbe042e43f96c05666'
SHA256='1d4b4f454ce1c416d6a1ab2369d6e66c0ff99e04390172eef70790499e21ce19'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=REPO.parent/'puzzle-private/hanzi-paint-bucket/idiom-source')
    args=parser.parse_args();output=args.output.resolve()
    if output==REPO or REPO in output.parents:parser.error('Use a directory outside the repository')
    output.mkdir(parents=True,exist_ok=True)
    for name,remote in [('idiom.json','data/idiom.json'),('LICENSE','LICENSE')]:
        target=output/name
        if target.exists():data=target.read_bytes()
        else:
            with urllib.request.urlopen(f'https://raw.githubusercontent.com/pwxcoo/chinese-xinhua/{COMMIT}/{remote}',timeout=90) as response:data=response.read()
        if name=='idiom.json' and hashlib.sha256(data).hexdigest()!=SHA256:
            raise ValueError('Dictionary hash differs from pinned source')
        if not target.exists():target.write_bytes(data)
    source={'repository':'https://github.com/pwxcoo/chinese-xinhua','commit':COMMIT,'sha256':SHA256,
        'entries':len(json.loads((output/'idiom.json').read_bytes())),'license':'MIT (repository declaration)'}
    (output/'source.json').write_text(json.dumps(source,indent=2)+'\n',encoding='utf8')
    print(json.dumps(source))


if __name__=='__main__':main()
