#!/usr/bin/python
"""Verify archive rewriting, checksum guards and cache construction with fixtures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

root = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('runtime_prepare', root/'runtime/prepare.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def archive(path, files):
    header = {'files':{}}
    position = 0
    for name, data in files.items():
        node = header
        parts = name.split('/')
        for part in parts[:-1]:node = node['files'].setdefault(part, {'files':{}})
        node['files'][parts[-1]] = dict(offset=str(position),size=len(data),integrity=dict(
            algorithm='SHA256',hash=m.sha(data),blockSize=4,
            blocks=[m.sha(data[i:i+4]) for i in range(0,len(data),4)]))
        position += len(data)
    raw=json.dumps(header,separators=(',',':')).encode()
    payload=struct.pack('<I',len(raw))+raw
    payload+=b'\0'*(-len(payload)%4)
    pickle=struct.pack('<I',len(payload))+payload
    path.write_bytes(struct.pack('<2I',4,len(pickle))+pickle+b''.join(files.values()))

class RuntimeTest(unittest.TestCase):
    def test_archive_rewrite_keeps_unmodified_bytes_and_repairs_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            archive(directory/'original',{'small':b'A','nested/changed':b'old','tail':b'tail-byte-data'})
            original=m.Archive(directory/'original')
            changed=b'longer\xe4\xb8\xad\xe6\x96\x87'
            original.write(directory/'new',{'nested/changed':changed})
            fixed=m.Archive(directory/'new')
            self.assertEqual(fixed.read('small'),b'A')
            self.assertEqual(fixed.read('tail'),b'tail-byte-data')
            self.assertEqual(fixed.read('nested/changed'),changed)
            entry=dict(fixed.entries())['nested/changed']
            self.assertEqual(entry['integrity']['hash'],m.sha(changed))
            self.assertEqual(entry['integrity']['blocks'],[m.sha(changed[i:i+4]) for i in range(0,len(changed),4)])

    def test_guarded_overlay_never_changes_vendor_and_reuses_cache(self):
        old_vendor,old_expected=m.VENDOR,m.EXPECTED
        try:
            with tempfile.TemporaryDirectory() as directory:
                directory=Path(directory)
                vendor=directory/'vendor';(vendor/'resources').mkdir(parents=True)
                (vendor/'typeless').write_bytes(b'executable fixture')
                (vendor/'libfixture.so').write_bytes(b'original library')
                (vendor/'resources/helper').write_bytes(b'helper')
                files={m.MAIN:b'main fixture;',m.ENTRY:m.RESULT_ANCHOR.encode()}
                archive(vendor/'resources/app.asar',files)
                before=(vendor/'resources/app.asar').read_bytes()
                m.VENDOR=vendor;m.EXPECTED={name:m.sha(data) for name,data in files.items()}
                binary=m.prepare(directory/'cache')
                self.assertEqual((vendor/'resources/app.asar').read_bytes(),before)
                self.assertFalse(binary.is_symlink())
                self.assertEqual((binary.parent/'libfixture.so').resolve(),vendor/'libfixture.so')
                self.assertIn(m.IPC.encode(),m.Archive(binary.parent/'resources/app.asar').read(m.ENTRY))
                self.assertEqual(binary,m.prepare(directory/'cache'))
                m.EXPECTED[m.ENTRY]='0'*64
                with self.assertRaisesRegex(ValueError,'Unsupported Typeless'):
                    m.prepare(directory/'cache')
                self.assertEqual((vendor/'resources/app.asar').read_bytes(),before)
        finally:
            m.VENDOR,m.EXPECTED=old_vendor,old_expected

if __name__=='__main__':unittest.main()
