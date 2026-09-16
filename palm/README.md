# Palm rejection (libinput quirks)

System-level palm tuning. Hyprland settings cannot set palm size. This ships
a tested `/etc/libinput/local-overrides.quirks` template.

Same file covers both Apple trackpads:

- `omarchy12`: Apple SPI via applespi (`touchpad + spi + 0x06CB`).
- `omarchy-air`: Apple MTP via Asahi (`touchpad + Apple*MTP*`).

Stock Apple threshold is `1600`. Template uses `1000`.
Lower is stronger. Use `800` if palms still slip.
Use `1200` if real edge touches get eaten.

## Install

```bash
sudo install -m 644 palm/local-overrides.quirks /etc/libinput/local-overrides.quirks
omarchy pkg add libinput-tools
libinput quirks list /dev/input/event5   # omarchy12 SPI
libinput quirks list /dev/input/event2   # omarchy-air MTP
sudo reboot
```

List output must show `AttrPalmSizeThreshold=1000` from
`local-overrides.quirks`. Reboot is required. Internal SPI and MTP
re-read quirks only at init.

## Verify

Type with palms resting. Pointer must stay put. Tap trackpad edges
with one finger. Taps must still register.
