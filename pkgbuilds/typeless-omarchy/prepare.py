#!/usr/bin/python
"""Build a private, version-checked runtime overlay; never edit vendor files."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

VENDOR = Path('/opt/Typeless')
MAIN = 'dist/main/bootstrapPrimaryInstance-D2WJURak.js'
ENTRY = 'dist/renderer/static/js/CLnu4epW.mjs'
EXPECTED = {
    MAIN: '8d14b7b340113c2bd52943e453bd8c37c3d381c434955765e3d403b66f201c8c',
    ENTRY: '83099ef43191ad8b38d30d6b3f89a43bb78b87ecbe98c1b98db7f6ca1a5c7c62',
}
IPC = "typeless-omarchy:has-input"
MAIN_HOOK = r'''
// Independent Typeless-Omarchy compatibility hook: no text or account data.
import {connect as typelessOmarchyConnect} from 'node:net';
_0x11c115.handle('typeless-omarchy:has-input', () => new Promise(resolve => {
  const runtime = process.env.XDG_RUNTIME_DIR;
  if (!runtime || !runtime.startsWith('/')) { resolve(false); return; }
  let done = false, reply = '';
  const socket = typelessOmarchyConnect(runtime + '/typeless-voice-ime/inject.sock');
  const finish = value => { if (!done) { done = true; socket.destroy(); resolve(value); } };
  socket.setTimeout(250, () => finish(false));
  socket.on('error', () => finish(false));
  socket.on('connect', () => socket.end('{"op":"status"}'));
  socket.on('data', data => { reply += data.toString(); if (reply.length > 64) finish(false); });
  socket.on('end', () => finish(reply === 'FOCUSED_EDITABLE'));
  socket.on('close', () => finish(false));
}));
'''
RESULT_ANCHOR = "if(!_0xebd390)return;const [_0x113491,_0x54fdc2]=await fr()"
RESULT_HOOK = """if(!_0xebd390)return;
if(!await window.ipcRenderer.invoke('typeless-omarchy:has-input')){
  await _0x814f0e(_0x296bb1.userPrompt??'',_0x166d45,_0x296bb1.webMetadata||{},_0xc7ce8);
  return;
}
const [_0x113491,_0x54fdc2]=await fr()"""

def sha(data):
    return hashlib.sha256(data).hexdigest()

class Archive:
    def __init__(self, path):
        self.path = path
        with path.open('rb') as stream:
            prefix = stream.read(16)
            _, header_size, _, json_size = struct.unpack('<4I', prefix)
            self.base = 8 + header_size
            self.header = json.loads(stream.read(json_size))

    def entries(self, node=None, prefix=''):
        node = self.header if node is None else node
        for name, entry in node['files'].items():
            path = prefix + name
            if 'files' in entry:
                yield from self.entries(entry, path + '/')
            elif 'offset' in entry:
                yield path, entry

    def read(self, name):
        entries = dict(self.entries())
        entry = entries[name]
        with self.path.open('rb') as stream:
            stream.seek(self.base + int(entry['offset']))
            return stream.read(entry['size'])

    def write(self, path, changed):
        entries = sorted(self.entries(), key=lambda item: int(item[1]['offset']))
        original = {name: (int(entry['offset']), entry['size']) for name, entry in entries}
        offset = 0
        for name, entry in entries:
            entry['offset'] = str(offset)
            if name in changed:
                data = changed[name]
                entry['size'] = len(data)
                if 'integrity' in entry:
                    block = entry['integrity']['blockSize']
                    entry['integrity'].update(hash=sha(data), blocks=[sha(data[i:i+block]) for i in range(0,len(data),block)])
            offset += entry['size']
        raw = json.dumps(self.header, separators=(',', ':'), ensure_ascii=False).encode()
        payload = struct.pack('<I', len(raw)) + raw
        payload += b'\0' * (-len(payload) % 4)
        pickle = struct.pack('<I', len(payload)) + payload
        with self.path.open('rb') as source, path.open('wb') as target:
            target.write(struct.pack('<2I', 4, len(pickle)) + pickle)
            for name, entry in entries:
                if name in changed:
                    target.write(changed[name])
                    continue
                position, remaining = original[name]
                source.seek(self.base + position)
                while remaining:
                    chunk = source.read(min(remaining, 1024*1024))
                    if not chunk: raise ValueError('Truncated vendor archive')
                    target.write(chunk)
                    remaining -= len(chunk)

def prepare(cache):
    archive = Archive(VENDOR / 'resources/app.asar')
    sources = {name: archive.read(name) for name in EXPECTED}
    for name, digest in EXPECTED.items():
        if sha(sources[name]) != digest:
            raise ValueError('Unsupported Typeless build; result compatibility patch was not applied')
    entry = sources[ENTRY].decode()
    if entry.count(RESULT_ANCHOR) != 1:
        raise ValueError('Vendor completion handler changed')
    changed = {MAIN: sources[MAIN] + MAIN_HOOK.encode(),
               ENTRY: entry.replace(RESULT_ANCHOR, RESULT_HOOK).encode()}
    vendor_stat = (VENDOR / 'typeless').stat()
    archive_stat = archive.path.stat()
    key = sha(Path(__file__).read_bytes() + str((vendor_stat.st_ino, vendor_stat.st_size, vendor_stat.st_mtime_ns,
              archive_stat.st_ino,archive_stat.st_size,archive_stat.st_mtime_ns)).encode())[:24]
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    final = cache / key
    if (final / 'ready').exists():
        return final / 'typeless'
    stage = Path(tempfile.mkdtemp(prefix='.prepare-', dir=cache))
    try:
        for child in VENDOR.iterdir():
            if child.name == 'resources': continue
            if child.name == 'typeless':
                # A symlink would resolve /proc/self/exe back to the vendor directory.
                subprocess.run(['cp', '--reflink=auto', str(child), str(stage / child.name)], check=True)
            else:
                (stage / child.name).symlink_to(child)
        resources = stage / 'resources'
        resources.mkdir()
        for child in (VENDOR / 'resources').iterdir():
            if child.name != 'app.asar': (resources / child.name).symlink_to(child)
        archive.write(resources / 'app.asar', changed)
        (stage / 'ready').write_text('Typeless 2.2.0; local compatibility overlay\n')
        try:
            stage.rename(final)
        except OSError:
            if not (final / "ready").exists():
                raise
        return final / 'typeless'
    finally:
        if stage.exists(): shutil.rmtree(stage)

if __name__ == '__main__':
    try:
        cache = Path(sys.argv[1]) if len(sys.argv)>1 else Path(os.environ.get('XDG_CACHE_HOME', Path.home()/'.cache'))/'typeless-omarchy/runtime'
        print(prepare(cache))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print('Typeless-Omarchy: '+str(error), file=sys.stderr)
        sys.exit(1)
