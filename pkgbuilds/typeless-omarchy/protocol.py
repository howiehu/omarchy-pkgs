#!/usr/bin/python
"""Exercise the compiled addon in an isolated Fcitx and D-Bus session."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

root = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix="typeless-protocol-") as directory:
    base = Path(directory)
    for path in ("data/fcitx5/addon", "data/fcitx5/inputmethod", "config", "runtime"):
        (base / path).mkdir(parents=True, mode=0o700)
    (base / "data/fcitx5/addon/typeless-voice.conf").write_text(
        (root / "data/typeless-voice-addon.conf").read_text().replace("OnDemand=True", "OnDemand=False").replace("Library=typeless-voice", "Library=" + str(root / "build/typeless-voice")))
    env = dict(os.environ, FCITX_ADDON_DIRS=str(root / "build"),
               FCITX_DATA_DIRS=str(base / "data"), XDG_DATA_HOME=str(base / "data"),
               XDG_CONFIG_HOME=str(base / "config"), XDG_RUNTIME_DIR=str(base / "runtime"))
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    log = (base / "fcitx.log").open("w+")
    server = subprocess.Popen(["dbus-run-session", "--", "fcitx5", "--disable=all",
                               "--enable=typeless-voice", "-D"], env=env, stdout=log, stderr=log,
                              start_new_session=True)
    path = base / "runtime/typeless-voice-ime/inject.sock"
    def request(payload):
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(2)
            connection.connect(str(path))
            connection.sendall(payload)
            connection.shutdown(socket.SHUT_WR)
            return connection.recv(4096).decode()
    try:
        for _ in range(40):
            if path.exists() or server.poll() is not None:
                break
            time.sleep(0.05)
        if not path.exists():
            log.seek(0)
            raise AssertionError(log.read())
        cases = [(b'{"op":"status"}', "UNFOCUSED"),
                 (b'{"op":"commit","text":"synthetic"}', "NO_FOCUS"),
                 (b'{"op":"commit","text":""}', "ERROR"),
                 (b'{"op":"commit","text":123}', "ERROR"),
                 (b'{"op":"commit","text":"a\\u0000b"}', "ERROR"),
                 (b'[]', "ERROR"), (b'not json', "ERROR"),
                 (b'{"op":"ping"} trailing', "ERROR"),
                 (b'{"text":"x"}', "ERROR"), (b'{"op":4}', "ERROR"),
                 (b'\xff', "ERROR")]
        for payload, expected in cases:
            actual = request(payload)
            assert actual == expected, (payload, expected, actual)
        assert path.stat().st_mode & 0o777 == 0o600
        # An incomplete connection must neither block Fcitx nor survive indefinitely.
        with socket.socket(socket.AF_UNIX) as slow:
            slow.settimeout(2)
            slow.connect(str(path))
            slow.sendall(b'{')
            assert request(b'{"op":"ping"}') == "UNFOCUSED"
            assert slow.recv(32) == b'TIMEOUT'
        assert request(b' ' * 65537) == "ERROR"
        assert request(b'{"op":"ping"}') == "UNFOCUSED"
        arguments = ["call", "--session", "--dest", "org.fcitx.Fcitx5", "--object-path",
                     "/controller", "--method", "org.fcitx.Fcitx.Controller1.CurrentInputMethod"]
        scoped = dict(env, TYPELESS_OMARCHY_ACTIVE="1", TYPELESS_OMARCHY_PID=str(os.getpid()),
                      DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent")
        helper = root / "helpers/gdbus"
        virtual = subprocess.run(["python", str(helper), *arguments], env=scoped, capture_output=True, text=True)
        assert virtual.returncode == 0 and virtual.stdout.strip() == "('typeless-voice',)"
        unscoped = subprocess.run(["python", str(helper), *arguments],
                                  env=dict(scoped, TYPELESS_OMARCHY_PID="-1"), capture_output=True)
        assert unscoped.returncode != 0, "Shim affected an unrelated caller"
        normal = subprocess.run(["python", str(helper), "help"], env=scoped, capture_output=True)
        system = subprocess.run(["/usr/bin/gdbus", "help"], env=scoped, capture_output=True)
        assert (normal.returncode, normal.stdout, normal.stderr) == (system.returncode, system.stdout, system.stderr)
        print(f"PASS: {len(cases)} protocol cases, private socket, slow/oversized clients")
        print("PASS: private query shim, caller scope and system-command passthrough")
    finally:
        import signal
        try:
            os.killpg(server.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        server.wait(timeout=4)
        log.close()
