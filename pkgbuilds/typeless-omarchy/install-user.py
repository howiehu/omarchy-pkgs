#!/usr/bin/python
"""Install/remove the prototype without touching the vendor app or system files."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

root = Path(__file__).resolve().parent.parent
home = Path.home()
data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
state_dir = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state")) / "typeless-omarchy"
state_file = state_dir / "install.json"
library = home / ".local/lib/fcitx5/typeless-omarchy-voice.so"
addon = data / "fcitx5/addon/typeless-voice.conf"

def call(method, signature=None, *args):
    command = ["busctl", "--user", "--json=short", "call", "org.fcitx.Fcitx5",
               "/controller", "org.fcitx.Fcitx.Controller1", method]
    if signature:
        command += [signature, *args]
    result = subprocess.check_output(command, text=True).strip()
    return json.loads(result)["data"] if result else None

def restart(previous):
    subprocess.run(["omarchy", "restart", "xcompose"], check=True)
    for _ in range(50):
        if subprocess.run(["fcitx5-remote", "--check"], stdout=subprocess.DEVNULL).returncode == 0:
            break
        time.sleep(0.1)
    if previous and previous != "typeless-voice":
        subprocess.run(["fcitx5-remote", "-s", previous], check=True)

if "--remove" in sys.argv:
    if not state_file.exists():
        raise SystemExit("No prototype installation record found")
    state = json.loads(state_file.read_text())
    current = call("CurrentInputMethod")[0]
    for path in (addon, library):
        path.unlink(missing_ok=True)
    restart(current if current != "typeless-voice" else state["previous"])
    state_file.unlink()
    print("Removed prototype; kept existing input methods and vendor package")
else:
    if Path("/usr/lib/fcitx5/typeless-voice.so").exists():
        raise SystemExit("Remove the packaged bridge before a development install")
    if state_file.exists() or any(path.exists() for path in (addon, library)):
        raise SystemExit("Prototype paths already exist; remove the previous prototype first")
    previous = call("CurrentInputMethod")[0]
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(dict(previous=previous)))
    for path in (addon, library):
        path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "build/typeless-voice.so", library)
    addon.write_text((root / "data/typeless-voice-addon.conf").read_text().replace(
        "Library=typeless-voice", "Library=" + str(library.with_suffix(""))))
    restart(previous)
    print("Installed user-level prototype; original input methods retained")
