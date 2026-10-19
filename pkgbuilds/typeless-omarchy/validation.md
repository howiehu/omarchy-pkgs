# Validation and deployment

The minimal reproduction is `python tests/live-input.py --terminal`. It opens an isolated Foot process running `read`, calls the same native `insertText` symbol as Typeless with synthetic text, and compares the captured result. It never types into an existing user shell. The test restores the original workspace and focus. On this machine Hyprland uses Lua dispatch, so the harness uses `hl.dsp.focus`.

Require the bridge, rather than accepting a vendor clipboard fallback:

```bash
python tests/live-input.py --require-ime
python tests/live-input.py --terminal --require-ime
python tests/live-input.py --terminal --require-ime --other-workspace
python tests/live-input.py --guard-password
python tests/live-input.py --guard-no-focus
```

The initial development prototype used these user-owned files:

- `~/.local/lib/fcitx5/typeless-omarchy-voice.so`
- `~/.local/share/fcitx5/addon/typeless-voice.conf`
- `~/.local/state/typeless-omarchy/install.json`
- `~/.local/bin/typeless-omarchy`
- `~/.config/hypr/typeless-compat.lua`
- An added `require("hypr.typeless-compat")` line and its preceding prototype comment in `~/.config/hypr/hyprland.lua`
- `~/.local/share/applications/typeless.desktop`, with its prior version saved as `typeless.desktop.bak.compat`

To undo the development plugin, run `python tools/install-user.py --remove`. Remove the exact prototype comment and require line from Hyprland's user config, then delete `~/.config/hypr/typeless-compat.lua`. Restore `typeless.desktop.bak.compat` to `typeless.desktop` and remove the user launcher. Run `hyprctl reload` and check `hyprctl configerrors`. The earlier pre-prototype config is also saved as `hyprland.lua.bak.typeless-*`; do not blindly restore it over later user changes.

Do not publish raw vendor logs or desktop screenshots: they may contain the user's dictated text or account information. The contribution report uses only synthetic test results and backend status tokens.

The test machine has since been migrated to the pacman-managed `typeless-omarchy 0.2.0-1` package. Its explicit desktop setup was disabled and enabled again successfully, followed by another passing GTK and cross-workspace Foot test. The package owns the Fcitx plugin, launcher, setup utility and optional Lua rule; user setup state is stored in `~/.local/state/typeless-omarchy/package.json`. The development plugin and its Lua include have been removed.

The first prototype registered a selectable `typeless-voice` input method. A new regression detected that Typeless warmup changed the actual method before restoring it. Version 0.2 replaces that engine with a passive module and a narrowly scoped per-process query adapter. The additional acceptance command is `python tests/live-input.py --terminal --require-ime --preserve-im --shuangpin`; it requires both exact text delivery and identical real input-method names before, during and after native warmup/commit.

Final 0.2 verification passed GTK and cross-workspace Foot tests with `--preserve-im --shuangpin`, plus `--interleave` for actual manual Chinese before/after the voice commit. The user confirmed real mixed Shuangpin/voice use and an English-mode switch while retaining the selected method. System `fcitx5-remote -n` reported `shuangpin` while Typeless was running; its private query saw the virtual endpoint and performed no real engine capture or switch.

The `Status` recording canvas persists after an application restart and is transparent while idle. With no workaround Hyprland draws a visible empty frame. The final rule removes decorations, blur and focus only for class `Typeless`, title `Status`; verified border_size=0 and no_focus=true plus local visual inspection. Only the recording canvas is pinned across workspaces. No dashboard rule, extra tray icon or visibility service is installed.

Version 0.4 result validation:

- A synthetic replay of the installed vendor completion handler fails before the patch: absent input context and an insertion-classified app produce one insertion and zero cards. After the patch, absent context (including a stale editable accessibility hint) produces zero insertions and one official card; a genuinely focused editable case preserves the vendor route.
- Run `node tests/result-routing.cjs <extracted-CLnu4epW.mjs>` against the original and privately patched archive entries to reproduce the before/after. The proprietary handler is read from the locally installed app, not included in the package.
- `python tests/runtime.py` checks archive offset/integrity repair, unchanged vendor bytes/resources, cache reuse and refusal of unsupported code hashes.
- A temporary loopback Electron diagnostic session ran the patched vendor completion handler with synthetic text, the real Fcitx status IPC and the real vendor card entry point on an empty workspace. The `AI result` window mapped, accepted focus and followed workspace changes. The recording HUD remained non-focusable. No speech/provider call was made for this test. Debug flags are not part of the normal launcher.
- The native constructors share a translated title key, but the renderer sets the actual interactive card title to `AI result`. The previous title-collision explanation did not establish the cause of the missing answer. Actual window observation and completion routing provide the evidence above.
