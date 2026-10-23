# Complete-frame composition validation, 2026-10-23

The desktop launcher now enables Weston's existing `WESTON_FORCE_RENDERER`
switch by default. `desktop.main.force_composition=0` unsets it; setting the
environment variable to `0` would still enable the Weston switch. No Weston
source or renderer changes are required. The option follows both native
systemd and procd startup paths, and older launcher argument lists retain
the default enabled behavior.

## Source and package checks

- `python3 scripts/tests/desktop-rdp-config.py`: three tests passed, including
  default, explicit enable, disable with an inherited environment variable,
  invalid input, GL/Pixman and RDP listener/configuration cases.
- `python3 scripts/tests/test-desktop-audio.py`: four tests passed.
- Shell syntax and `git diff --check` passed.
- A direct `openwrt-desktop` package build produced signed version `14`.
  Extracted launcher contents matched the source. `.config` and the existing
  unrelated PipeWire recipe changes were preserved.

## Physical host

The existing ordinary-user SSH connection and sudo were used. The host
verified the new and rollback package signatures using its existing keys.
The exact offline simulation upgraded only `openwrt-desktop` from `13` to `14`;
the same package was installed. The APK world file was restored after checking
that APK had only reordered entries and replaced the desktop constraint with
a local-package content pin. No feed publication was performed.

After setting `desktop.main.force_composition=1` and restarting the desktop,
the live Weston process exported `WESTON_FORCE_RENDERER=1` and retained
`--renderer=gl`. Weston and Sunshine were active with their existing LAN
listeners. A temporary isolated Firefox profile was launched on this desktop;
the DRM snapshot showed only the Weston-owned primary plane active, with no
client overlay plane. The test browser was stopped and its temporary profile
removed. No VM test, reboot or Moonlight-client visual acceptance was performed.

The first restart exposed abandoned VNC/RDP listener sockets inherited by
existing terminal descendants, preventing rebinding and triggering Weston's
backend-failure cleanup abort. Disabling force composition reproduced the
same startup failure. Only the two identified abandoned listening sockets
were shut down through duplicated process descriptors; their owning processes
were retained. Weston then started successfully with force composition enabled.

Network, firewall, DHCP, Passwall, SSH, desktop TLS identities, Sunshine settings
and pairing-state hashes matched their backups. The boot ID was unchanged.
Rollback package, configuration backup and diagnostics remain in the root-only
directory `/root/weston-composition-fix-20261023` on the host. The temporary
rollback timer was stopped after recovery.
