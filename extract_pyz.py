import marshal, zlib, os, sys

src = sys.argv[1]
outdir = sys.argv[2]
os.makedirs(outdir, exist_ok=True)

with open(src, 'rb') as f:
    assert f.read(4) == b'PYZ\x00', 'not a PYZ'
    pymagic = f.read(4)
    (toc_pos,) = __import__('struct').unpack('!i', f.read(4))
    f.seek(toc_pos)
    toc = marshal.load(f)
    if isinstance(toc, list):
        toc = dict(toc)
    print('py magic', pymagic.hex(), 'entries', len(toc))
    count = 0
    for key, (ispkg, pos, length) in toc.items():
        f.seek(pos)
        name = key.decode('utf-8') if isinstance(key, bytes) else key
        try:
            raw = zlib.decompress(f.read(length))
        except Exception:
            continue
        if ispkg == 1:
            path = os.path.join(outdir, name.replace('.', os.sep), '__init__.pyc')
        else:
            path = os.path.join(outdir, name.replace('.', os.sep) + '.pyc')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as g:
            g.write(pymagic + b'\x00' * 12)
            g.write(raw)
        count += 1
    print('wrote', count)