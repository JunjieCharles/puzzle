"""Explicit user exclusions only; concrete words live outside the repository."""


def editorial_exclusions(entries, policy):
    """No POS or inferred semantic filtering; apply only the explicit private list."""
    excluded={}
    for row in policy['excluded_words']:
        if not isinstance(row.get('word'),str) or not row['word'] or not row.get('reason'):
            raise ValueError('Each private exclusion requires a word and reason')
        excluded[row['word']]=row['reason']
    characters=policy.get('excluded_characters',[])
    for row in characters:
        if not isinstance(row.get('character'),str) or len(row['character'])!=1 or not row.get('reason'):
            raise ValueError('Each private character exclusion requires one character and reason')
    positions=policy.get('excluded_character_positions',[])
    for row in positions:
        if (not isinstance(row.get('character'),str) or len(row['character'])!=1
                or type(row.get('position')) is not int or row['position']<1 or not row.get('reason')):
            raise ValueError('Positional exclusion requires one character, positive 1-based position and reason')
    for entry in entries:
        for row in characters:
            if row['character'] in entry['word']:
                excluded[entry['word']]=row['reason']
        for row in positions:
            word=entry['word'];index=row['position']-1
            if index<len(word) and word[index]==row['character']:
                excluded[word]=row['reason']
    return excluded


def two_character_component_exclusions(words, policy, component_areas):
    """Apply the private structural list only to two-character candidates.

    Count original paint regions of at least 25 px; do not mutate image masks
    or the competitor dictionary. Structural membership is independently
    checked against a pinned IDS source when maintaining the private policy.
    """
    characters=policy.get('two_character_single_component_characters',[])
    if any(not isinstance(c,str) or len(c)!=1 for c in characters):
        raise ValueError('Structural exclusions require individual characters')
    banned={c for c in characters if sum(a>=25 for a in component_areas[c])==1}
    return {w for w in words if len(w)==2 and set(w)&banned},banned
