"""Final candidate list for translation, with per-string provenance and flags."""
import json, re, marshal, types
from collections import defaultdict

inv = json.load(open('inventory.json', encoding='utf-8'))

# docstrings
docstrings = set()
for m in ['pyz_out/UVR.pyc', 'pyz_out/gui_data/constants.pyc',
          'pyz_out/gui_data/old_data_check.pyc', 'pyz_out/separate.pyc',
          'pyz_out/gui_data/error_handling.pyc']:
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

BAD = re.compile(r'https?://|models/|\.pth|\.onnx|\.json|\.py|\\\\b|^\\|^\[|:\d|C:|E:|/Users/|/home/|#[0-9a-fA-F]{3,8}|^\d|^[a-z_]+$|^\(|^MB|\{|\}$')

def keyish(s):
    if re.fullmatch(r'[a-z0-9_./\- ]*', s) and '_' in s:
        return True
    if s.isupper() and len(s) > 3:
        return True
    if re.fullmatch(r'[a-z0-9]+', s):
        return True
    return False

cands = {}
for s, meta in inv.items():
    if meta['in_logic'] or meta['persisted']:
        continue
    if s in docstrings:
        continue
    if not re.search(r'[A-Za-z]{2}', s):
        continue
    if keyish(s) or BAD.search(s):
        continue
    # strings whose only home is error_handling = error signatures -> skip
    paths = meta['paths']
    if paths and all('error_handling' in p for p in paths):
        continue
    if len(s.strip()) == 0:
        continue
    cands[s] = sorted(paths)

print('final candidates:', len(cands))

# classify by rough visibility: label (short, no newline) vs message/help
labels = sorted([s for s in cands if '\n' not in s and len(s) <= 40], key=lambda s: (len(s), s))
longs = sorted([s for s in cands if '\n' in s or len(s) > 40], key=lambda s: -len(s))
print('short labels:', len(labels), ' long/multiline:', len(longs))

with open('final_candidates.txt', 'w', encoding='utf-8') as f:
    f.write('===== SHORT LABELS (%d) =====\n' % len(labels))
    for s in labels:
        f.write(repr(s) + '\n')
    f.write('\n===== LONG / MULTILINE (%d) =====\n' % len(longs))
    for s in longs:
        f.write(repr(s) + '\n')
json.dump(cands, open('final_candidates.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('wrote final_candidates.txt / .json')