# Typeless-Omarchy

An independent Fcitx5 bridge and small desktop integration for the official Typeless 2.2.0 Linux application. The installed vendor files are never edited or redistributed. Version 0.4 also builds a private runtime copy for the guarded answer-card patch described below.

The official build attempts to switch Fcitx5 to `typeless-voice`, but ships no Fcitx5 addon binary. It falls back to simulated clipboard paste. On the tested Omarchy system, this reaches GTK entries but fails in Foot while the vendor log reports success. This addon implements the existing local VoiceIME protocol and uses Fcitx's `commitString` instead. Version 0.2 is a passive Fcitx module, not a selectable input method: it leaves the user's active keyboard/Chinese engine and preedit state alone. No clipboard polling, transcript database access, or speech-provider replacement is involved.

## Keeping the existing input method

The vendor's input helper normally queries `CurrentInputMethod` through `gdbus`, selects `typeless-voice`, then restores an earlier engine. That breaks concurrent typing and may restore a stale selection. The launcher gives only Typeless a private helper directory in PATH. Its `gdbus` adapter answers exactly that engine query with the virtual voice endpoint, only when called directly by the launcher's recorded process and the bridge socket responds. Every other caller and command executes the system `gdbus`. The real Fcitx D-Bus service, global PATH and input-method group are unchanged.

The module commits to the genuinely focused Fcitx input context, regardless of the current engine. No extra voice engine is added to the user's switcher. This is a compatibility contract with Typeless 2.2.0, not a published vendor API; changes to the vendor helper require revalidation.

## Ask Anything answer recovery

Typeless 2.2.0 can classify a selected-text command as `delivery=replace`, attempt insertion without a focused input context, then skip its answer card based on application insertion rules. The native helper can report clipboard-paste success without visible delivery. This is independent of window decoration: a real answer card maps as `AI result`, while the recording HUD maps as `Status`.

Before the vendor's **Ask Anything replace** handler inserts, a private main-process IPC handler checks the existing Fcitx bridge's focus status. With no focused, non-sensitive input context it opens the vendor's original interactive answer card and skips the paste attempt. With a focused editable context it preserves the vendor handler. Reply, external actions, ordinary dictation and voice translation routing are unchanged. This preflight does not guarantee delivery after a later focus change or fix the vendor's rich-text insertion path.

The launcher generates a private copy under `${XDG_CACHE_HOME:-~/.cache}/typeless-omarchy/runtime/`. It copies the official executable, links unchanged runtime resources, and rewrites two files in a private ASAR archive. The patch checks exact SHA-256 fingerprints for the tested 2.2.0 main/renderer code, updates archive integrity entries, and caches the result. Unsupported builds use the base input bridge with a warning; no unrecognized code is patched. The package contains only the independent transformation, not vendor code or generated archives. No account/history access, persistent debugger, extra service or extra UI is used by this feature.

Set `TYPELESS_OMARCHY_BASE_ONLY=1` when launching to bypass the runtime copy. Exit Typeless fully before switching modes because the vendor enforces a single instance. Generated cache files can be removed after exiting the app. User login, preferences and deep links use the same profile as the official application.

## Scrolling redraw compatibility

On the tested Wayland desktop, scrolling long official answer cards with GPU acceleration produces rectangular text displacement/flicker. The user confirmed that the same synthetic long card scrolls normally after launching only Typeless with `--disable-gpu`. The launcher therefore uses software rendering for this app by default; other applications and compositor settings are untouched. Set `TYPELESS_OMARCHY_GPU=1` before launching to re-enable the vendor's hardware rendering for comparison. Exit the existing instance first. Software rendering can use more CPU; this workaround is not a claim that every GPU/Wayland setup requires it.

## Tested

On Omarchy 4.0.5, Hyprland 0.56.2, Fcitx5 5.1.23 and Typeless 2.2.0-1, x86_64:

- Before: `python tests/live-input.py --terminal` failed to deliver the synthetic text, although the vendor reported clipboard-paste success.
- After: GTK and Foot received the exact synthetic Chinese/English text using the official `insertText` function and the new VoiceIME backend.
- Foot input on a second workspace passed, with the original workspace and focus restored afterwards.
- Missing input context and password-entry tests rejected commits.
- An isolated D-Bus/Fcitx session passed malformed JSON, wrong types, embedded NUL, invalid UTF-8, oversized and stalled-connection tests. The socket is private and accepts only the current UID.
- The user successfully dictated and submitted a real Chinese message. With 0.2, the user also confirmed mixed manual Shuangpin/voice input and switching to English without losing the selected input method.
- `--preserve-im --shuangpin` asserts identical real engine names before, during and after native warmup/commit. `--interleave` types Chinese through the actual keyboard/input-method path, commits voice text, then types Chinese again.
- The transparent `Status` recording canvas receives no border, shadow, background blur or focus. Without this exact-title workaround Hyprland exposes an empty 750x500 rectangle. Only this recording canvas is pinned across workspaces, so dictation status follows workspace changes. The official dashboard, tray, login and onboarding behavior remain unchanged. Interactive `AI result` cards are also pinned across workspaces and retain focus/click handling.

The earlier vendor application disappearance has no confirmed cause. The successful tests do not prove long-term crash freedom. Selected-text editing, surrounding-text queries and rich-text insertion are outside this prototype. The vendor may still choose its own fallback for those features. This bridge refuses password/sensitive contexts; it cannot guarantee the vendor's separate fallback behavior.

## Build

Dependencies: CMake, C++20 compiler, Fcitx5 headers, json-c, GLib, Python and dbus-run-session.

```bash
cmake -S . -B build -DCMAKE_INSTALL_PREFIX=/usr
cmake --build build
ctest --test-dir build --output-on-failure
```

Build an Arch package using `python tools/stage-package.py /tmp/typeless-compat-package`, then run `makepkg` in that directory. The generated recipe contains local source files and real SHA-256 checksums; it downloads no vendor application. Install the official `typeless-bin` separately through Omarchy's AUR installer.

## Packaged desktop integration

After installing the compatibility package, run `typeless-omarchy-setup` as your desktop user. It leaves the input-method group unchanged, points the user's Typeless desktop entry to the Wayland launcher, and adds only the exact-title recording-canvas compatibility rule. It backs up the desktop entry. Launch Typeless from the app menu; existing vendor autostart entries are not changed automatically.

Before removing the package, run `typeless-omarchy-setup --remove`. This restores the previous desktop entry and removes its exact config include. If that entry was edited afterwards, the removal refuses to overwrite it.

`tools/install-user.py` is a development-only plugin installer. It copies the passive addon into a user directory without changing the input-method group. Remove it with `python tools/install-user.py --remove`. It does not manage the separately installed development launcher/window rule; see `docs/validation.md` for their paths and rollback steps. Do not keep a development plugin installed alongside the packaged plugin.

## Contribution

The intended package contribution is to `omacom/omarchy-pkgs`. Package-local sources are supplied because this is a new compatibility implementation, with no independently published release feed. Automatic upstream synchronization is disabled pending a maintainer decision about source ownership. Desktop integration is opt-in; there is no system install hook that changes user profiles or restarts input methods.

The bridge is MIT licensed. Typeless and its Electron/Chromium notices retain their own terms.
