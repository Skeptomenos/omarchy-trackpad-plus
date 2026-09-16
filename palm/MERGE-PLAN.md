# Palm rejection plus Mac gestures in Trackpad Plus fork

Goal: Trackpad Plus fork manages libinput palm rejection and keeps david.trackpad Mac gestures.
Acceptance: `palm/` ships tested quirks template plus install script. Gestures support fullscreen-up and scratchpad-down. Existing suite passes.
Scope: Fork `Skeptomenos/omarchy-trackpad-plus` branch `palm-mac-merge`. No release yet. No UI wiring in this increment.
Context: Upstream `d6d35e1` synced 2026-09-16. Upstream has DWT toggle but no palm quirks. Local `david.trackpad` has 4-finger Mac gestures. Live proof: `/etc/libinput/local-overrides.quirks` with `AttrPalmSizeThreshold=1000` stops jumps on omarchy12 Apple SPI.

## Next increments

- [ ] Palm scaffold: quirks template plus install and verify script, with test. Check with `python3 -m pytest` or repo test runner and `libinput quirks list`.
- [ ] Mac gestures port: fullscreen-up and scratchpad-down options in `gestures.py` plus schema note. Check with gesture tests.
- [ ] Panel wiring: palm slider and privileged install prompt in `Panel.qml`. Check live on omarchy12 and omarchy-air.

## Progress (LIVING)

- 2026-09-16: Fork synced to upstream `d6d35e1` and pushed. Branch `palm-mac-merge` cut. Plan written. Next: add `palm/` scaffold.
- 2026-09-16: Palm scaffold merged (`palm/` template, README, test). Mac gestures ported: `fullscreen_up` plus `scratchpad_down`, schema 8, editor toggles, 8 new tests. Full Python suite passes (104). qmllint clean. qmltestrunner not installed locally.
- 2026-09-17: Live check on omarchy12 passed. Horizontal swipe, up fullscreen, down scratchpad all work. Down needs a window in scratchpad; empty scratchpad shows nothing. That is Hyprland drag-threshold behavior, not a bug.
- 2026-09-17: Air validated at 1000. No cursor jumps. Both hosts clean. Default stays 1000.
- 2026-09-17: Panel slider done. Pointer tab has rejection slider, status line, install button. qmllint and IPC offscreen pass. Next: live panel check on omarchy12.

## Decision Log (LIVING)

- 2026-09-16: Use upstream as base. It already covers per-device DWT, tap, Apple detection. Local panel retires after port. Rationale: one plugin, no ID conflict.
