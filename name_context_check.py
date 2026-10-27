"""Check how constants are *used* from UVR.pyc, via their names.

Usage: py -3.9 name_context_check.py <strings.json>

constants.pyc stores UI text as module-level names such as
CHOOSE_PROC_METHOD_MAIN_LABEL. UVR.pyc only ever loads those names, so the
literal never appears there. This script maps each value to its name(s), then
looks at every use of that name in UVR.pyc and flags comparisons, dict
subscripts, containment tests and console/file operations.
"""
import dis
import json
import marshal
import sys

RISKY_NEARBY = ('COMPARE_OP', 'CONTAINS_OP')
RISKY_ATTRS = ('get', 'join', 'format', 'split', 'encode', 'decode', 'lower',
               'upper', 'strip', 'insert', 'config', 'configure', 'set',
               'load', 'loads', 'dump', 'dumps', 'open', 'write')
SAFE_CALLS = ('Label', 'Button', 'Radiobutton', 'Checkbutton', 'Combobox',
              'Entry', 'Frame', 'text', 'title', 'messagebox', 'showinfo',
              'showerror', 'showwarning', 'askyesno', 'tooltip', 'ToolTip')


def load_code(path):
    with open(path, 'rb') as f:
        data = f.read()
    try:
        return marshal.loads(data)
    except Exception:
        return marshal.loads(data[16:])


def walk(code, out=None):
    if out is None:
        out = []
    out.append(code)
    for const in code.co_consts:
        if hasattr(const, 'co_code'):
            walk(const, out)
    return out


def assignments(path):
    """name -> value for `NAME = 'string'` including inside class bodies."""
    pairs = {}
    for code in walk(load_code(path)):
        ins = list(dis.get_instructions(code))
        for i, x in enumerate(ins):
            if x.opname not in ('STORE_NAME', 'STORE_GLOBAL'):
                continue
            j = i - 1
            while j >= 0 and ins[j].opname == 'EXTENDED_ARG':
                j -= 1
            if j >= 0 and ins[j].opname == 'LOAD_CONST' and isinstance(ins[j].argval, str):
                pairs.setdefault(ins[j].argval, set()).add(x.argval)
    return pairs


def uses(path, names):
    found = {}
    for code in walk(load_code(path)):
        ins = list(dis.get_instructions(code))
        for i, x in enumerate(ins):
            if x.opname not in ('LOAD_NAME', 'LOAD_GLOBAL', 'LOAD_ATTR', 'LOAD_METHOD'):
                continue
            if x.argval not in names:
                continue
            window = ins[max(0, i - 6):i + 8]
            ops = [w.opname for w in window]
            attrs = [w.argval for w in window
                     if w.opname in ('LOAD_ATTR', 'LOAD_METHOD', 'LOAD_GLOBAL', 'LOAD_NAME')]
            risky = [o for o in ops if o in RISKY_NEARBY]
            risky += [a for a in attrs if isinstance(a, str) and a in RISKY_ATTRS]
            safe = [a for a in attrs if isinstance(a, str) and a in SAFE_CALLS]
            found.setdefault(x.argval, []).append(
                (code.co_name, sorted(set(risky)), safe))
    return found


def main():
    strings = json.load(open(sys.argv[1], encoding='utf-8'))
    names = assignments('pyz_out/gui_data/constants.pyc')
    usage = uses('UVR.exe_extracted/UVR.pyc', {n for s in names.values() for n in s})

    for value in strings:
        owners = sorted(names.get(value, []))
        if not owners:
            print(f'{value!r:44} <no module-level name>')
            continue
        for owner in owners:
            entries = usage.get(owner, [])
            if not entries:
                print(f'{value!r:44} {owner:34} <never loaded from UVR.pyc>')
                continue
            for scope, risky, safe in entries:
                tag = 'RISK' if risky else 'ok  '
                print(f'{value!r:44} {owner:34} {tag} risky={risky} safe={safe[:4]} in {scope}')


if __name__ == '__main__':
    main()
