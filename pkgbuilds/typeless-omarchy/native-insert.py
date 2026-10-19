#!/usr/bin/python
"""Call the same native insertion entry point as the official application."""
import ctypes
import sys
import subprocess
import os
from pathlib import Path

os.environ["TYPELESS_OMARCHY_PID"] = str(os.getpid())
os.environ["TYPELESS_OMARCHY_ACTIVE"] = "1"
os.environ["PATH"] = str(Path(__file__).resolve().parent.parent / "helpers") + ":" + os.environ["PATH"]

def current():
    return subprocess.check_output(["/usr/bin/fcitx5-remote", "-n"], text=True).strip()

helper = ctypes.CDLL("/opt/Typeless/resources/lib/input-helper/build/linux/x64/libInputHelper.so")
helper.insertText.argtypes = [ctypes.c_char_p]
helper.insertText.restype = None
before = current()
helper.warmup_voice_ime()
print("IM_BEFORE=" + before, flush=True)
print("IM_DURING=" + current(), flush=True)
helper.insertText(sys.argv[1].encode())
helper.restore_voice_ime()
helper.cleanup_input_helper()
print("IM_AFTER=" + current(), flush=True)
