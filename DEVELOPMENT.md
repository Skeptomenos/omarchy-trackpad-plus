# Per-device trackpad controls

This branch began with the working customization copied from the installed
`local.touchpads` plugin; review fixes now preserve the upstream `awkent01.touchpad`
identity and direct IPC interface. The Git history and `origin` remote come from
<https://github.com/awkent01/omarchy-touchpad-widget>.

## Changes

- Apple/Dell selector with independent settings for each trackpad.
- Both Apple Magic Trackpad interfaces share the Apple settings.
- Pointer speed, scroll speed, acceleration, and tap/click controls apply only
  to the selected device.
- Adaptive/flat pointer acceleration with migration from the previous settings.
- A Python helper serializes writes and persists per-device Lua configuration.
- Pending slider adjustments stay assigned to their original device when
  switching the selector.

## Development

```sh
python3 test_trackpads.py
node test-selection.js
python3 test_install.py
python3 test_ipc.py
git diff --cached
```

The workspace is a separate copy; edits here do not change the installed panel.
The README describes the current implementation. Older screenshots and legacy
helper scripts are retained for reference. `Panel.qml` uses `trackpads.py`.

The installation test copies only Git-tracked files into temporary storage and
uses a fake compositor. Stage newly added source files before running it. The
UI regression test executes functions extracted from `Panel.qml` with controlled
callback ordering and also runs the actual timeout wrapper against a stalled
child process. These checks do not replace a live multi-monitor UI check.

## Before submitting upstream

This is a snapshot of the working local plugin, not a finished upstream patch.
Prepare the contribution by reconciling:

- The retained `local-touchpads` state paths with upstream preferences. They
  currently preserve compatibility with the previously installed customization.
- Device labels/grouping (the Dell label currently recognizes one hardware ID).
- Screenshots and obsolete helpers with the final implementation.

Do not commit runtime settings or personal configuration backups. No settings
files were copied into this checkout.
