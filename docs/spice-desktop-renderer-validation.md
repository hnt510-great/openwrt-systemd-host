# SPICE OpenGL desktop renderer repair

Validated on 2026-10-14 on the physical OpenWrt host at 192.0.2.1.

## Cause and change

The saved Weston configuration selected `pixman`. An ordinary-user GTK
GLArea therefore used Mesa softpipe and did not expose
`EGL_EXT_image_dma_buf_import`. Importing QEMU's SPICE scanout failed with
`EGL_BAD_PARAMETER` (0x300c), including the BIOS's 640x480 and 720x400 buffers.
The QEMU process remained alive. A private GL compositor used Intel UHD
Graphics (JSL) and imported the same buffers successfully.

`openwrt-desktop` release 12 defaults to `gl` in its packaged configuration,
init-script fallback, and session-script fallback. `desktop-setup` enrolls
the user in both `video` and `render`; the package explicitly depends on
`accel-support`, which creates the render group. Explicit `pixman` remains
available. Existing conffiles retain their saved renderer on package upgrades;
the physical host was explicitly migrated with UCI and its desktop restarted.
No automatic renderer fallback was added.

## Local build

The following checks completed successfully:

* `python3 scripts/tests/desktop-rdp-config.py` (three test methods, including
  GL and pixman with/without RDP and the five-argument GL session default).
* `sh -n` on the changed init, setup, and session scripts.
* `make package/custom/openwrt-desktop/compile -j4 V=s`.
* `make package/install -j4 V=s` and `make target/install -j4 V=s`.
* `git diff --check`; the original `.config` checksum is unchanged.

The built squashfs contains `renderer='gl'`; the image manifest records
`openwrt-desktop - 12`.

| Artifact | SHA256 |
| --- | --- |
| `bin/systemd/packages/x86_64/base/openwrt-desktop-12.apk` | `304f102256bc55eb0b6bed587ec46bd145a70f98ea49ad3e693b8ebcdc7ebb66` |
| `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz` | `49c8b6626398c84469e6efbf77c31a7f9d85d2aa7838ca0dfb4be58c4dd950ea` |

The rebuilt image was inspected but was not cold-boot tested or flashed in
this run. Physical runtime evidence below applies to the signed package
upgrade and saved configuration on the existing installation.

## Physical deployment and verification

`apk verify` accepted the new APK with the host's existing trusted keys.
The offline simulated transaction upgraded only `openwrt-desktop` from
11 to 12; the real transaction matched. Installed init, setup, and session
script checksums match the source files. The kernel/kmod package inventory
and network, firewall, DHCP, and system configuration checksums are unchanged.
The router was not rebooted.

The normal Weston session now runs `--renderer=gl` with its existing DRM,
VNC, and RDP backends and 1920x1080 mode. The ordinary desktop user reports
`Mesa Intel(R) UHD Graphics (JSL)`; both BIOS buffer imports pass with EGL
success (0x3000). VNC 5900 and RDP 3389 remain bound to the LAN address.
Desktop, procd, and virtqemud are active, and LAN HTTPS responds with 200.
No new desktop-service errors were recorded after the renderer migration.
Fresh external VNC/RDP authentication was not exercised in this run.

The temporary VGA/SPICE 2D fallback displayed the installer initially but
lost portions of the image after console reconnection. The user's `win2k25`
VM was returned to VirtIO video with 3D enabled and SPICE OpenGL using
`/dev/dri/renderD128`, retaining the Windows ISO as the first boot device.
Only this guest was restarted, while it was at the installer screen.

Windows Server Setup's language-selection screen is visible through the
actual virt-manager GtkGLArea after reconnection. A framebuffer capture
shows the complete dialog, and a SPICE Tab-key input changes focus/pixels;
Shift-Tab restores focus. The VM and its console remain open at language
selection. No Windows installation or experimental Windows driver test
was performed. This is 2D installer/input verification through the OpenGL
console path, not Windows guest 3D acceleration acceptance.

Evidence and captures are in
[`spice-desktop-fix-20261014`](/srv/openwrt-validation/spice-desktop-fix-20261014).
The physical host's configuration/script/XML backups are in
`/srv/libvirt/diagnostics/spice-desktop-fix-20261014/`.
