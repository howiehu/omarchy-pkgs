#!/usr/bin/python
"""Run synthetic native insertion against a dedicated GTK window, restoring focus."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys
import time
import socket

here = Path(__file__).resolve().parent
def hypr(*args):
    return subprocess.check_output(["hyprctl", *args], text=True)

original = json.loads(hypr("activewindow", "-j")).get("address")
workspace = json.loads(hypr("activeworkspace", "-j"))["id"]
env = dict(os.environ, GTK_IM_MODULE="fcitx", GDK_BACKEND="wayland")
with tempfile.TemporaryDirectory(prefix="typeless-probe-") as directory:
    output = Path(directory) / "received.txt"
    terminal = "--terminal" in sys.argv
    guard = "--guard-password" in sys.argv or "--guard-no-focus" in sys.argv
    command = (["foot", "--app-id=typeless-compat-probe", "--title=Typeless compatibility probe", "bash", "-c", 'IFS= read -r line; printf "%s" "$line" > "$1"; sleep 3', "probe", str(output)]
               if terminal else ["python", str(here / "input-probe.py"), str(output)])
    if "--guard-password" in sys.argv:
        command.append("--password")
    if "--guard-no-focus" in sys.argv:
        command.append("--no-entry")
    if "--other-workspace" in sys.argv:
        used = [w["id"] for w in json.loads(hypr("workspaces", "-j"))]
        hypr("dispatch", 'hl.dsp.focus({ workspace = "' + str(max(used) + 1) + '" })')
    probe = subprocess.Popen(command, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        address = None
        for _ in range(50):
            for client in json.loads(hypr("clients", "-j")):
                if client["pid"] == probe.pid:
                    address = client["address"]
            if address:
                break
            time.sleep(0.1)
        assert address, "Probe window was not created"
        hypr("dispatch", 'hl.dsp.focus({ window = "address:' + address + '" })')
        time.sleep(0.3)
        assert json.loads(hypr("activewindow", "-j"))["address"] == address
        if "--shuangpin" in sys.argv:
            subprocess.run(["fcitx5-remote", "-s", "shuangpin"], check=True)
        token = "Omarchy兼容输入验证-42"
        prefix = ""
        if "--interleave" in sys.argv:
            assert not terminal and not guard, "Interleave test uses the GTK text entry"
            subprocess.run(["wtype", "ni "], check=True)
            time.sleep(0.2)
            prefix = output.read_text() if output.exists() else ""
            assert any(ord(char) > 127 for char in prefix), "Manual Chinese input did not commit"
        if guard:
            previous = subprocess.check_output(["fcitx5-remote", "-n"], text=True).strip()
            try:
                time.sleep(0.2)
                with socket.socket(socket.AF_UNIX) as connection:
                    connection.settimeout(2)
                    connection.connect(os.environ["XDG_RUNTIME_DIR"] + "/typeless-voice-ime/inject.sock")
                    connection.sendall(json.dumps({"op":"commit", "text": token}).encode())
                    connection.shutdown(socket.SHUT_WR)
                    reply = connection.recv(100).decode()
                expected = "PASSWORD" if "--guard-password" in sys.argv else "NO_FOCUS"
                assert reply in ({"PASSWORD", "NO_FOCUS"} if expected == "PASSWORD" else {expected}), (expected, reply)
                assert not output.exists(), "Guard allowed text into the target"
                print("PASS: input guard " + expected)
                raise SystemExit(0)
            finally:
                subprocess.run(["fcitx5-remote", "-s", previous], check=True)
        result = subprocess.run(["python", str(here / "native-insert.py"), token + ("\n" if terminal else "")],
                                env={k:v for k,v in env.items() if k != "DISPLAY"},
                                capture_output=True, text=True, timeout=8)
        for _ in range(20):
            if output.exists() and output.read_text() == prefix + token:
                break
            time.sleep(0.1)
        passed = result.returncode == 0 and output.exists() and output.read_text() == prefix + token
        if "--require-ime" in sys.argv:
            passed = passed and "backend=voice-ime status=succeeded" in result.stderr
        if "--preserve-im" in sys.argv:
            methods = dict(line.split("=", 1) for line in result.stdout.splitlines() if line.startswith("IM_"))
            preserved = methods.get("IM_BEFORE") == methods.get("IM_DURING") == methods.get("IM_AFTER")
            print("PASS: input method unchanged" if preserved else "FAIL: input method changed: " + str(methods))
            passed = passed and preserved
        if "--interleave" in sys.argv and passed:
            subprocess.run(["wtype", "ni "], check=True)
            time.sleep(0.2)
            text = output.read_text()
            passed = text.startswith(prefix + token) and len(text) > len(prefix + token)
            print("PASS: manual Chinese, voice commit, manual Chinese" if passed else "FAIL: manual typing after voice")
        print(("PASS" if passed else "FAIL") + ": native insertion " + ("reached " if passed else "did not reach ") + ("terminal" if terminal else "GTK input"))
        for line in result.stderr.splitlines():
            if any(x in line for x in ("backend=", "stage=", "status=", "failed")):
                print(line)
        raise SystemExit(0 if passed else 1)
    finally:
        probe.terminate()
        probe.wait(timeout=3)
        hypr("dispatch", 'hl.dsp.focus({ workspace = "' + str(workspace) + '" })')
        if original:
            hypr("dispatch", 'hl.dsp.focus({ window = "address:' + original + '" })')
