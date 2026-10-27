"""Print usage context for a set of strings so risky ones can be spotted by hand.

Usage: py -3.9 context_check.py <module.pyc> "str" ["str" ...]
"""
import dis
import marshal
import sys


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


DIALOG = ('showinfo', 'showerror', 'showwarning', 'askyesno', 'askokcancel',
          'title', 'config', 'configure', 'insert', 'set', 'Label', 'Button',
          'Radiobutton', 'Checkbutton', 'Combobox', 'text', 'messagebox')


def main():
    path, targets = sys.argv[1], set(sys.argv[2:])
    for code in walk(load_code(path)):
        try:
            ins = list(dis.get_instructions(code))
        except Exception:
            continue
        for i, x in enumerate(ins):
            if x.opname != 'LOAD_CONST' or not isinstance(x.argval, str) or x.argval not in targets:
                continue
            window = ins[max(0, i - 6):i + 7]
            ops = [w.opname for w in window]
            attrs = [w.argval for w in window if w.opname in ('LOAD_ATTR', 'LOAD_METHOD', 'LOAD_GLOBAL')]
            flag = ''
            if any(o in ('COMPARE_OP', 'CONTAINS_OP') for o in ops):
                flag = '  <<< COMPARISON'
            if any(a in DIALOG for a in attrs if isinstance(a, str)):
                flag = flag + '  [dialog]'
            print(f'{x.argval!r:42} {code.co_name:34} {attrs}{flag}')


if __name__ == '__main__':
    main()
