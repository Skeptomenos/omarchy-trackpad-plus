# Touchpad — Omarchy bar widget

A bar widget for [Omarchy](https://omarchy.org) with independent controls for
multiple trackpads. Select a device at the top of the panel before adjusting it.

## Controls

- Enable or disable the selected trackpad.
- Scroll speed (0.1–2.0) and pointer speed (−1.0–1.0).
- Pointer acceleration: adaptive when on, flat when off. Adaptive acceleration
  makes faster finger movements travel farther; it uses libinput's native curve.
- Natural scrolling, tap to click, disable while typing, and clickfinger behavior.
- Keyboard navigation through device selection, sliders, and switches.

Both Apple Magic Trackpad interfaces share one set of Apple settings. The known
Dell touchpad is labeled Dell; other devices containing `touchpad` or `trackpad`
in their Hyprland name are listed by that name. Disconnected devices retain their
saved settings, and newly attached devices are discovered during state refreshes.

## Requirements and installation

Requires Omarchy's Quickshell shell and Lua-based Hyprland configuration, Python 3,
`hyprctl`, and GNU `timeout` (coreutils).

```sh
omarchy plugin add https://github.com/awkent01/omarchy-touchpad-widget.git --enable
```

The upstream plugin ID remains `awkent01.touchpad`. For an existing checkout:

```sh
omarchy plugin enable awkent01.touchpad
```

Settings initialize automatically on the first state read. Existing legacy
pointer settings are imported where recognized. Subsequent reads preserve saved
settings; changing one device does not replace another device's settings.

Structural QML changes require a shell restart if hot reload leaves the old
component running:

```sh
omarchy restart shell
```

## Keyboard commands and IPC

The inherited Omarchy panel handler exposes the existing command target:

```sh
omarchy-shell awkent01.touchpad open
omarchy-shell awkent01.touchpad close
omarchy-shell awkent01.touchpad toggle
omarchy-shell awkent01.touchpad show
omarchy-shell awkent01.touchpad hide
```

## Persistence and process behavior

`trackpads.py` serializes state reads and writes with a file lock and writes
settings using temporary files and atomic replacement. Settings are stored under
`$XDG_STATE_HOME`, defaulting to `~/.local/state`:

- `omarchy/local-touchpads/settings.json` stores per-device values.
- `omarchy/toggles/hypr/zz-local-touchpads.lua` contains literal per-device rules
  loaded by Omarchy on Hyprland configuration reloads.

These paths retain compatibility with the initial local customization. The
helper emits per-device `hl.device` rules, not shared `hl.config` settings. On a
reported save failure it attempts to restore the previous selected-device rules.
The two files are replaced individually, not as one filesystem transaction.

The panel bounds state reads to 15 seconds and writes to 10 seconds, followed by
a two-second forced-kill deadline. A timed-out action releases the queue and
reports an error. Poll responses captured before a newer edit are discarded and
replaced with a fresh read after pending work finishes.

The panel displays its saved settings. Changes made by separate configuration
tools are not automatically imported into the saved per-device values.

## Development and verification

```sh
python3 test_trackpads.py
node test-selection.js
python3 test_install.py
python3 test_ipc.py  # On an Omarchy host; requires local IPC sockets
```

The installation test copies only Git-tracked files into a temporary plugin
folder, uses temporary state and a fake compositor, and checks first-run setup,
independent writes, device discovery, and recovery from a blocked lock. Stage
new source files before running this test.

The UI tests execute functions extracted from the actual QML source with
controlled callback ordering. They exercise device switching, stale reads,
debounced edits, timeout recovery, and command configuration. They also verify
the timeout wrapper against a real stalled child process. A live Omarchy UI
check is still appropriate before release.

## Uninstall

```sh
omarchy plugin remove awkent01.touchpad
```

Removing the plugin does not remove the saved state or generated device rules.
To reset those overrides, remove the two state files listed above and reload
Hyprland; back up any settings you want to preserve first.

## License

MIT. Based on the original widget by awkent01.
