"""Build a string inventory for UVR localization: candidates + safety exclusions.

Collects, across the modules we plan to patch:
  * every string constant (with the code path where it appears)
  * strings used in comparisons / membership tests / dict-subscript lookups
  * persisted values found in UVR's data.pkl (read via pickletools = no code exec)
Outputs inventory.json.
"""
import marshal, dis, sys, types, json, pickletools, io, re
from collections import defaultdict

MODULES = [
    'pyz_out/UVR.pyc',
    'pyz_out/gui_data/constants.pyc',
    'pyz_out/gui_data/error_handling.pyc',
    'pyz_out/gui_data/old_data_check.pyc',
    'pyz_out/separate.pyc',
]


def walk(code, path=''):
    yield path or '<module>', code
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield from walk(c, (path + '/' + c.co_name) if path else c.co_name)


def collect(path):
    data = open(path, 'rb').read()[16:]
    root = marshal.loads(data)
    strings = defaultdict(list)   # value -> [code paths]
    logic = set()                 # used in compare / subscr / kwargs keys
    for name, co in walk(root):
        for c in co.co_consts:
            if isinstance(c, str):
                strings[c].append(name)
            elif isinstance(c, (tuple, list)):
                for x in c:
                    if isinstance(x, str):
                        strings[x].append(name + '[]')
            elif isinstance(c, dict):
                for k, v in list(c.items()):
                    for x in (k, v):
                        if isinstance(x, str):
                            strings[x].append(name + '{}')
        try:
            instrs = list(dis.get_instructions(co))
        except Exception:
            continue
        for i, ins in enumerate(instrs):
            prev = instrs[i-1] if i else None
            if ins.opname in ('COMPARE_OP', 'CONTAINS_OP') and prev and prev.opname == 'LOAD_CONST':
                if isinstance(prev.argval, str):
                    logic.add(prev.argval)
            if ins.opname == 'BINARY_SUBSCR' and prev and prev.opname == 'LOAD_CONST' \
               and isinstance(prev.argval, str):
                logic.add(prev.argval)
            # kwargs key tuples: LOAD_CONST ('text', ...); CALL_FUNCTION_KW
            if ins.opname == 'CALL_FUNCTION_KW' and prev and prev.opname == 'LOAD_CONST' \
               and isinstance(prev.argval, tuple):
                for k in prev.argval:
                    if isinstance(k, str):
                        logic.add(k)
    return strings, logic


def pkl_values(path):
    """Extract string values from a pickle without executing it."""
    out = set()
    data = open(path, 'rb').read()
    for op, arg, pos in pickletools.genops(data):
        if op.name in ('BINUNICODE', 'SHORT_BINUNICODE', 'UNICODE', 'BINSTRING', 'SHORT_BINSTRING') \
           and isinstance(arg, (str, bytes)):
            s = arg.decode('utf-8', 'replace') if isinstance(arg, bytes) else arg
            out.add(s)
    return out


def main():
    all_strings = defaultdict(set)
    logic = set()
    for m in MODULES:
        try:
            s, l = collect(m)
        except FileNotFoundError:
            print('skip (missing):', m)
            continue
        for k, v in s.items():
            all_strings[k].update(v)
        logic |= l
        print(f'{m}: {len(s)} distinct strings, {len(l)} logic strings')

    try:
        persisted = pkl_values('E:/UVR5/data.pkl')
        print('data.pkl strings:', len(persisted))
    except Exception as e:
        persisted = set()
        print('data.pkl read failed:', e)

    inventory = {}
    for s, paths in sorted(all_strings.items()):
        inventory[s] = {
            'paths': sorted(paths),
            'in_logic': s in logic,
            'persisted': s in persisted,
        }

    json.dump(inventory, open('inventory.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    # quick stats for triage
    def is_keyish(s):
        return bool(re.fullmatch(r'[a-z0-9_./\-]+', s)) or s.isupper()

    cands = [s for s, m in inventory.items()
             if not m['in_logic'] and not m['persisted']
             and ' ' in s and not is_keyish(s)]
    print('total distinct strings :', len(inventory))
    print('in logic               :', sum(1 for m in inventory.values() if m['in_logic']))
    print('persisted in data.pkl  :', sum(1 for m in inventory.values() if m['persisted']))
    print('sentence-like candidates:', len(cands))
    json.dump(sorted(cands), open('candidates.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()