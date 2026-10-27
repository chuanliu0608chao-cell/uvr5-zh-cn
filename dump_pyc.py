"""Dump module-level assignments and function-level string consts in a pyc."""
import marshal, dis, sys, types

def fmt(v, limit=3000):
    r = repr(v)
    return r if len(r) <= limit else r[:limit] + '...'

def dump_module(co, indent=''):
    """Emit 'NAME = value' for top-level assignments."""
    instrs = list(dis.get_instructions(co))
    pending = None
    for ins in instrs:
        op = ins.opname
        if op in ('LOAD_CONST',):
            pending = ins.argval
        elif op.startswith('BUILD_'):
            pending = f'<{op} x{ins.argval}>'
        elif op == 'STORE_NAME':
            if isinstance(pending, str) or (pending is not None and not str(pending).startswith('<')):
                print(f'{indent}{ins.argval} = {fmt(pending)}')
            else:
                print(f'{indent}{ins.argval} = {fmt(pending)}')
            pending = None
        elif op in ('LOAD_GLOBAL', 'LOAD_NAME', 'IMPORT_NAME', 'LOAD_ATTR', 'CALL_FUNCTION',
                    'CALL_FUNCTION_KW', 'POP_TOP', 'ROT_TWO', 'DUP_TOP', 'BUILD_TUPLE',
                    'BUILD_LIST', 'BUILD_MAP', 'BUILD_CONST_KEY_MAP', 'MAKE_FUNCTION'):
            if op in ('CALL_FUNCTION', 'CALL_FUNCTION_KW', 'MAKE_FUNCTION', 'IMPORT_NAME'):
                pending = None

def main(path, mode):
    data = open(path, 'rb').read()[16:]
    root = marshal.loads(data)
    if mode == 'module':
        dump_module(root)
    elif mode == 'funcs':
        def walk(c, path=''):
            yield path or '<module>', c
            for x in c.co_consts:
                if isinstance(x, types.CodeType):
                    yield from walk(x, (path + '/' + x.co_name) if path else x.co_name)
        for name, co in walk(root):
            strs = [c for c in co.co_consts if isinstance(c, str)]
            if strs:
                print(f'--- {name} (line {co.co_firstlineno})')
                for s in strs:
                    print('    ', fmt(s, 400))

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'module')