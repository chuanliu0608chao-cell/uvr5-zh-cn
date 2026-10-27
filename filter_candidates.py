"""Filter candidates down to genuine user-visible text."""
import json, re

cands = json.load(open('final_candidates.json', encoding='utf-8'))

IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$')
FILEISH = re.compile(r'\.[A-Za-z0-9]{2,5}$')
MISC_KEY = {
    'utf-8', 'python "', 'sel.last', 'sel.first', 'xdg-open', 'Fernet', 'KThread',
    'ConfigDict', 'TEntry', 'TLabel', 'TButton', 'TCombobox', 'TCheckbutton',
    'TRadiobutton', 'TMenubutton', 'Listbox', 'TkinterDnD', 'ConvertModel',
    'ModelParameters', 'CPUExecutionProvider', 'CUDAExecutionProvider',
    'HDemucs', 'MVSep', 'FFmpeg', 'Is Linux', 'full', 'N_FFT',
}

def is_internal(s):
    s2 = s.strip()
    if s2 in MISC_KEY:
        return True
    if s2.startswith(('<', '.', '/', '\\', '#', '[')):
        return True
    if IDENT.match(s2):
        return True
    if '/' in s2 and ' ' not in s2:
        return True
    if FILEISH.search(s2) and ' ' not in s2:
        return True
    if re.fullmatch(r'[a-z0-9_]+', s2):
        return True
    if re.fullmatch(r'[A-Z0-9_]+', s2) and '_' in s2:
        return True
    # tk style class names / theme tokens
    if re.fullmatch(r'T[A-Z][A-Za-z]+', s2):
        return True
    # pure numbers / units
    if re.fullmatch(r'[\d.\s%()-]+', s2):
        return True
    return False

kept, dropped = {}, []
for s, paths in cands.items():
    if is_internal(s):
        dropped.append(s)
    else:
        kept[s] = paths

labels = sorted([s for s in kept if '\n' not in s], key=lambda s: (len(s), s))
longs = sorted([s for s in kept if '\n' in s], key=lambda s: -len(s))

print('kept:', len(kept), '(short', len(labels), '/ multiline', len(longs), ')')
print('dropped:', len(dropped))

with open('translate_list.txt', 'w', encoding='utf-8') as f:
    f.write('===== UI LABELS (%d) =====\n' % len(labels))
    for s in labels:
        f.write(repr(s) + '\n')
    f.write('\n===== MULTILINE MESSAGES / HELP (%d) =====\n' % len(longs))
    for s in longs:
        f.write(repr(s) + '\n')
json.dump(kept, open('translate_list.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)
print('wrote translate_list.txt (%d lines)'
      % (len(labels) + len(longs) + 4))