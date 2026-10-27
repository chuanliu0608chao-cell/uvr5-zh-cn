"""Analyze UVR.pyc / constants.pyc: find display-only UI strings vs logic strings."""
import marshal, dis, sys, types, json
from collections import defaultdict

DISPLAY_KW = {'text', 'message', 'title', 'label', 'tooltip', 'prompt',
              'placeholder', 'heading', 'subtext', 'description', 'msg', 'caption'}
DISPLAY_FUNCS = ('tooltip', 'showinfo', 'showerror', 'showwarning', 'askyesno',
                 'askokcancel', 'messagebox', 'title', 'heading', 'insert',
                 'config', 'configure', 'set', 'message', 'caption')


def walk(code, path=''):
    yield path or '<module>', code
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield from walk(c, (path + '/' + c.co_name) if path else c.co_name)


def analyze(path):
    data = open(path, 'rb').read()[16:]
    root = marshal.loads(data)
    display = defaultdict(list)   # string -> contexts
    compared = set()              # strings used in comparisons
    allstr = set()

    for name, co in walk(root):
        try:
            instrs = list(dis.get_instructions(co))
        except Exception:
            continue
        # collect strings involved in comparisons
        for i, ins in enumerate(instrs):
            if ins.opname in ('COMPARE_OP',) and i >= 1:
                prev = instrs[i-1]
                if prev.opname == 'LOAD_CONST' and isinstance(prev.argval, str):
                    compared.add(prev.argval)
            if ins.opname == 'CONTAINS_OP' and i >= 1:
                prev = instrs[i-1]
                if prev.opname == 'LOAD_CONST' and isinstance(prev.argval, str):
                    compared.add(prev.argval)
            if ins.opname == 'LOAD_CONST' and isinstance(ins.argval, str):
                allstr.add(ins.argval)

        # find display-positioned strings
        n = len(instrs)
        for i, ins in enumerate(instrs):
            if ins.opname == 'LOAD_CONST' and isinstance(ins.argval, str):
                s = ins.argval
                # pattern: LOAD_CONST s; LOAD_CONST ('text',...); CALL_FUNCTION_KW
                if i + 2 < n and instrs[i+1].opname == 'LOAD_CONST' \
                   and isinstance(instrs[i+1].argval, tuple) \
                   and instrs[i+2].opname == 'CALL_FUNCTION_KW':
                    kw = instrs[i+1].argval
                    if any(k in DISPLAY_KW for k in kw):
                        display[s].append(f'{name}:{ins.starts_line}')
                    continue
                # pattern: {'text': s, ...} -> LOAD_CONST s, LOAD_CONST keys, BUILD_CONST_KEY_MAP
                if i + 2 < n and isinstance(instrs[i+1].argval, tuple) \
                   and any(k in DISPLAY_KW for k in instrs[i+1].argval) \
                   and instrs[i+2].opname == 'BUILD_CONST_KEY_MAP':
                    display[s].append(f'{name}:{ins.starts_line}')
                    continue
                # pattern: method call like .title(...) / .config(text=...)
                if i >= 1 and instrs[i-1].opname == 'LOAD_ATTR' \
                   and instrs[i-1].argval in DISPLAY_FUNCS:
                    display[s].append(f'{name}:{ins.starts_line}')
                    continue
                # pattern: called function whose name mentions tooltip/messagebox
                if i >= 1 and instrs[i-1].opname == 'LOAD_GLOBAL' \
                   and any(f in str(instrs[i-1].argval).lower() for f in ('tooltip', 'messagebox')):
                    display[s].append(f'{name}:{ins.starts_line}')

    return root, display, compared, allstr


def module_string_consts(root):
    """Top-level (module) co_consts strings and container members."""
    direct, in_containers = [], []
    for c in root.co_consts:
        if isinstance(c, str):
            direct.append(c)
        elif isinstance(c, (tuple, list)):
            for x in c:
                if isinstance(x, str):
                    in_containers.append(x)
        elif isinstance(c, dict):
            for k, v in c.items():
                if isinstance(v, str):
                    in_containers.append(v)
                if isinstance(k, str):
                    in_containers.append(k)
    return direct, in_containers


for path in sys.argv[1:]:
    root, display, compared, allstr = analyze(path)
    mod_direct, mod_container = module_string_consts(root)
    print('=' * 70)
    print(path)
    print('total distinct strings in code:', len(allstr))
    print('display-positioned strings    :', len(display))
    print('strings used in comparisons   :', len(compared))
    risky = [s for s in display if s in compared]
    print('RISKY (display AND compared)  :', len(risky))
    for s in risky[:30]:
        print('   ', repr(s))
    print('module-level direct strings   :', len(set(mod_direct)))
    print('strings inside containers     :', len(set(mod_container)))
    out = {
        'display': {s: ctx for s, ctx in display.items()},
        'compared': sorted(compared),
        'module_direct': sorted(set(mod_direct)),
        'module_container': sorted(set(mod_container)),
    }
    with open(path.replace('.pyc', '.analysis.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('wrote', path.replace('.pyc', '.analysis.json'))