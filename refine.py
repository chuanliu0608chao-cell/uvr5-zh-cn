"""Refine candidates: drop docstrings, key-like, logic, persisted. Group by module."""
import json, re, marshal, dis, types, sys
from collections import defaultdict

inv = json.load(open('inventory.json', encoding='utf-8'))

# collect docstrings from the modules
docstrings = set()
for m in ['pyz_out/UVR.pyc', 'pyz_out/gui_data/constants.pyc',
          'pyz_out/gui_data/error_handling.pyc', 'pyz_out/gui_data/old_data_check.pyc',
          'pyz_out/separate.pyc']:
    try:
        root = marshal.loads(open(m, 'rb').read()[16:])
    except Exception:
        continue
    def walk(c):
        yield c
        for x in c.co_consts:
            if isinstance(x, types.CodeType):
                yield from walk(x)
    for co in walk(root):
        if co.co_consts and isinstance(co.co_consts[0], str) and len(co.co_consts[0]) > 1:
            docstrings.add(co.co_consts[0])

def keyish(s):
    return bool(re.fullmatch(r'[a-z0-9_./\-]+', s)) or s.isupper() or '\n' in s

groups = defaultdict(list)
for s, meta in inv.items():
    if meta['in_logic'] or meta['persisted']:
        continue
    if ' ' not in s:
        continue
    if keyish(s):
        continue
    if s in docstrings:
        continue
    if not re.search(r'[A-Za-z]{2}', s):
        continue
    mods = tuple(sorted({p.split('/')[1] if '/' in p else p for p in meta['paths']}))
    groups[mods].append(s)

print('docstrings found:', len(docstrings))
total = 0
for g, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    print(f'{len(items):5d}  {g}')
    total += len(items)
print('TOTAL candidates:', total)

out = {'|'.join(g): sorted(v) for g, v in groups.items()}
json.dump(out, open('candidates2.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# show a spread of samples from the biggest group
big = max(groups.values(), key=len)
print('\n--- sample from largest group ---')
for s in sorted(big, key=len)[:40]:
    print('  ', repr(s))