"""Structural membership for paint-class exceptions, not answer data."""
import hashlib
import re

IDS_SHA256='bfc70a8c09f9f5616ebf0543bd6681e67314e9f7ae2307e5ae8c6f15bdc5c6a6'


def load_components(path):
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=IDS_SHA256:
        raise ValueError('Structural IDS snapshot differs from reviewed version')
    graph={}
    for line in raw.decode('utf8').splitlines():
        parts=line.split('\t')
        if line.startswith('#') or len(parts)<3:
            continue
        variants=[s for s in parts[2:] if '[' not in s or any('G' in tag for tag in re.findall(r'\[([^]]+)\]',s))]
        if not variants:
            variants=parts[2:3]
        graph[parts[1]]=set(''.join(re.sub(r'\[[^]]+\]','',s) for s in variants))
    return graph


def contains_component(character,target,graph):
    pending=[character];seen=set()
    while pending:
        c=pending.pop()
        if c==target:
            return True
        if c not in seen:
            seen.add(c);pending.extend(graph.get(c,()))
    return False


def structural_paint_classes(characters,component_areas,graph):
    """Count only regions >=25 px; preserve all original masks elsewhere."""
    moon=set();kai=set()
    for c in characters:
        count=sum(a>=25 for a in component_areas[c])
        if count==2 and contains_component(c,'月',graph):
            moon.add(c)
        if count==1 and contains_component(c,'开',graph):
            kai.add(c)
    return moon,kai
