#!/usr/bin/python
"""Synthetic input target. Never reads another application's text."""
import sys
from pathlib import Path
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

output = Path(sys.argv[1])
window = Gtk.Window(title="Typeless compatibility probe")
window.set_wmclass("typeless-compat-probe", "typeless-compat-probe")
window.set_default_size(560, 160)
entry = Gtk.Entry()
if "--password" in sys.argv:
    entry.set_visibility(False)
entry.connect("changed", lambda e: output.write_text(e.get_text()))
window.add(Gtk.Label(label="No editable input") if "--no-entry" in sys.argv else entry)
window.connect("destroy", Gtk.main_quit)
window.show_all()
entry.grab_focus()
Gtk.main()
