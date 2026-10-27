"""Produce the definitive translation list with strict junk filtering."""
import json, re, marshal, types

cands = json.load(open('translate_list.json', encoding='utf-8'))  # already junk-filtered once
inv = json.load(open('inventory.json', encoding='utf-8'))

# strings whose *definition* lives in error_handling.pyc = error signatures
err_defs = set()
try:
    root = marshal.loads(open('pyz_out/gui_data/error_handling.pyc', 'rb').read()[16:])
    for c in root.co_consts:
        if isinstance(c, str):
            err_defs.add(c)
except Exception as e:
    print('err module read failed:', e)

DOC_OK = set()  # nothing

LICENSE_KW = re.compile(
    'Permission is hereby|copies of the Software|furnished to do so|without restriction|'
    'to use, copy, modify|substantial portions|above copyright notice|Copyright \\(c\\) 2022|'
    'MIT Licensed|of this software and associated|accuracy or availability|Website Links|'
    'You acknowledge and agree|endorse any content|responsible for the contents|'
    'other websites and downloads|additional convenience|or activating such links|'
    'do not screen|make no representations|dependencies needed to run|This bundle contains|'
    'models or code for projects|Text Widget which is thread safe|Permission is hereby')

QUALNAME = re.compile(r'<locals>|<lambda>|<listcomp>|<genexpr>|<dictcomp>|<module>')
EXC_NAME = re.compile(r'^[A-Z][a-zA-Z]+(Error|Exception|Warning)$')
TRACEBACK = re.compile(r'::|Traceback|line \d+|NoneType|has no attribute|'
                       r'must be greater|is too big|BFCArena|AllocateRaw|'
                       r'is neither a single|referenced before assignment|'
                       r'CUDNN error|kernel image|DefaultCPUAllocator|Got invalid dimensions')

HARD_EXCLUDE = {
    'Montserrat', 'Century Gothic', 'Montserrat.ttf', 'GOTHIC.ttf', 'Tsurumeso',
    'Bas Curtiz', 'DilanBoskan', 'Adefossez & Demucs', 'Kuielab & Woosung Choi',
    'X-Minus AI', 'MVSep', 'FFmpeg', 'Rubber Band Library', 'Matchering',
    'Dim_f', 'Dim_t', '-topmost', 'kara check', 'ensemble check',
    'MDX-NET_Noise_Profile_14_kHz', 'MDX-NET_Noise_Profile_17_kHz',
    'MDX-NET_Noise_Profile_Full_Band', 'TFC_TDF_net', 'UVR_Patch_10_6_23_4_27',
    'No tab named \'', 'Is Linux', 'User Input', 'UTF-8',
    'Anjok07\\nAufr33',
}

def is_junk(s):
    t = s.strip()
    if t.startswith(('<', '.', '/', '#')) and len(t) < 40:
        return True
    if s in err_defs or s in HARD_EXCLUDE:
        return True
    if QUALNAME.search(s) and '<locals>' in s:
        return True
    if EXC_NAME.match(s.strip()):
        return True
    if TRACEBACK.search(s):
        return True
    if LICENSE_KW.search(s):
        return True
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_<>\[\]]+)+', s.strip()):
        return True   # dotted identifiers / qualnames
    return False

kept, dropped = {}, []
for s, paths in cands.items():
    if is_junk(s):
        dropped.append(s)
    else:
        kept[s] = paths

labels = sorted([s for s in kept if '\n' not in s], key=lambda s: (len(s), s))
multis = sorted([s for s in kept if '\n' in s], key=lambda s: -len(s))
print('TO TRANSLATE:', len(kept), '=', len(labels), 'labels +', len(multis), 'multiline')
print('dropped junk :', len(dropped))

with open('todo_labels.txt', 'w', encoding='utf-8') as f:
    for s in labels:
        f.write(repr(s) + '\n')
with open('todo_multis.txt', 'w', encoding='utf-8') as f:
    for s in multis:
        f.write(repr(s) + '\n')
json.dump(kept, open('todo.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('wrote todo_labels.txt / todo_multis.txt / todo.json')
