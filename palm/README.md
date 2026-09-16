# Palm rejection (libinput quirks)

System-level palm tuning. Hyprland settings cannot set palm size. This ships
a tested `/etc/libinput/local-overrides.quirks` template.

Same file covers both Apple trackpads:

- `omarchy12`: Apple SPI via applespi (`touchpad + spi + 0x06CB`).
- `omarchy-air`: Apple MTP via Asahi (`touchpad + Apple*MTP*`).

Stock Apple threshold is `1600`. Template uses `1000`.
Lower is stronger. Use `800` if palms still slip.
Use `1200` if real edge touches get eaten.

## Manage with palm-settings

```bash
palm/palm-settings get            # staged threshold
palm/palm-settings set 800        # stage 800 for both stanzas (100-1600)
palm/palm-settings status         # staged vs installed vs active
palm/palm-settings install        # copy to /etc (sudo in terminal, pkexec from UI)
```

`install` uses `sudo` in a terminal and `pkexec` from a graphical caller.
Reboot after install. Internal trackpads re-read quirks only at init.

## Panel slider

The Pointer tab shows a Palm rejection slider (100-1600, step 50),
a status line (staged, installed, active, reboot hint), and an
Install system quirks button. Moving the slider stages via
`palm-settings set`; install prompts for privilege and asks for a reboot.

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
