# Developing Trackpad Plus

Clone the independent repository and work outside the installed plugin:

```sh
git clone https://github.com/davefano/omarchy-trackpad-plus.git
cd omarchy-trackpad-plus
```

`main` is the maintained release line. Preserve original Git history and MIT
notices. Contributions should describe the observable behavior and validation.
Do not commit runtime settings, private configuration, caches, or backups.

## Release versions

Use `YYYY.MM.DD.N`, starting with `2026.09.13.0`. The date is the release
date, with zero-padded month and day; `N` starts at 0 and increases for each
release on that date. Compare the four components numerically, not as text
(revision 10 follows revision 9). Never reuse a published version or move the
date backward.

Before publishing a release, update `version` in `manifest.json`. The main
widget reads that file for its footer, so there is only one version to update.
This release identifier is separate from the backend's settings schema version.

## Architecture

- `Panel.qml`: Omarchy bar widget, device selection, debounced action queue,
  deadlines, and rejection of stale reads.
- `CurveEditor.qml` / `Curve.js`: draft curve editing, spinners, presets, and
  target practice. Only Apply changes the live profile.
- `trackpads.py`: device discovery, validation, file locking, persistence, and
  per-device `hl.device` updates. The libinput validator creates configuration
  objects without opening devices. Keep its sampled curve in sync with Curve.js.
- `Model.js`: numeric helpers and inherited legacy parsing utilities.
- `touchpad-state` / `touchpad-sensitivity`: inherited legacy CLI helpers,
  retained for compatibility; the current panel uses `trackpads.py` instead.

The `apple` settings group intentionally retains the original grouping of Apple
Magic Trackpad interfaces and now recognizes the built-in Apple trackpad. These
Apple devices share settings when connected together. The `dell` ID recognizes
one known Dell hardware name; other trackpads use their compositor device name.
New groups have `configured: false` until their first explicit edit; generated
Lua omits these groups. Missing `configured` means true for compatibility with
existing saved settings. Failed first edits restore the original configuration
with a config-only reload because reapplying an empty Lua block cannot remove a
runtime device override.
Scroll scale is per-group settings metadata. The backend stores the effective
`scroll_factor`, and the panel displays that value divided by `scroll_scale`.
Scale changes rescale the effective value in the same journaled transaction;
queued slider edits must commit under their old scale first. Schema 4 migration
adds scale metadata without changing effective factors or generated Lua.
The editor also uses that scale as its vertical gain limit. Saved curves stay in
absolute gain units; changing the axis does not rescale them. Newly selected
Mac-inspired presets fit the available range, and the backend applies the exact
validated curve supplied by the editor, including when restoring a preset.
Do not change saved group IDs or historical state paths without a migration.

## Complete automated suite

Run on an Omarchy host with Python 3, Node.js, libinput, Quickshell, Qt 6 Quick
Controls/Test, and Qt development tools (`qmllint`, `qmltestrunner`):

```sh
python3 test_trackpads.py
node test-selection.js
python3 test_install.py
python3 test_ipc.py
python3 lint-qml.py
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE=Basic \
  /usr/lib/qt6/bin/qmltestrunner -input tst_curve.qml
perl -c touchpad-state
bash -n touchpad-sensitivity
git diff --check
```

`lint-qml.py` runs qmllint over every QML source using the installed Omarchy
modules. It fails on all errors and warnings except specifically identified
missing metadata for Omarchy's dynamic bar/style properties and Quickshell's
`QProcess::ExitStatus`. These host API limitations are listed by the checker;
new or unrelated warnings fail. The editor and its test must lint without any
warnings. IPC and live checks cover the installed host interfaces.

Installation tests copy Git-tracked files into temporary storage, use a fake
compositor, and verify initialization, device isolation, discovery, migration,
persistence, blocked locks, oversized compositor responses, and recovery after
terminating a live edit. Backend tests inject failures at each persistence file,
check recovery journals, reject unsafe state paths and future schemas, and
exercise repeated file/native operations for descriptor leaks. Stage new runtime source files
before running them. No real settings are changed by automated tests.

Node tests execute actual Panel.qml functions with controlled callback ordering.
The Qt tests exercise keyboard/mouse input, fine and Shift steps, typed Apply,
curve bounds, preview, undo, and layout. Python compares the JS curve with the
native payload and checks actual libinput acceptance, including rejection of
the former oversized 81-point payload. IPC tests use a separate offscreen shell
and temporary sockets to verify all five commands against Omarchy's base Panel.

## Live installation and release checks

Use the README's backup and migration procedure. For an unpublished checkout,
copy the tracked runtime files and manifest into a new user plugin directory
named `davefano.trackpad-plus`, validate it with `omarchy plugin validate`, and
rescan with `omarchy-shell shell rescanPlugins`. Disable the previous widget
before enabling this one. Never edit `/usr/share/omarchy`.

Before publishing:

1. Run the full suite and validate the manifest.
2. Check the bar icon, main panel, device selection, profiles, curve/spinners,
   and target practice. Multi-device isolation is also covered by fixtures.
3. Apply a reversible profile change, check the saved values and generated Lua,
   and restore the original settings, including the previous-profile record.
4. Restart the shell and reload Hyprland; verify persistence and
   `hyprctl configerrors`. Check `systemctl --user --failed`, `systemctl --failed`,
   and Quickshell logs for newly introduced failures.
5. Keep a recovery copy of the previous plugin, shell layout, and state.

Check source diffs, images, license, and history before committing. Publish only
a verified clean tree. The upstream repository and the former personal fork
remain separate from this project's `origin`.
