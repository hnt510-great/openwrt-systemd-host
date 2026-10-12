# Physical Intel SPICE acceleration crash repair

Validated on 2026-10-12 against the existing x86_64/glibc native-systemd
installation. The physical GPU is Intel UHD Graphics (JSL), PCI 8086:4e61,
using i915 and Mesa 26.2.2. This validation uses the physical Intel render
node, rather than the previous nested AMD-backed test environment.

## Diagnosis and changes

Two distinct crashes were present in the host journal and domain logs:

* At 12:57:32 UTC, SPICE asserted in `spice_qxl_gl_scanout()` because a
  scanout was replaced while the previous GL draw cookie was outstanding.
  A disposable VM reproduces this by resetting QEMU before acknowledging
  the client's draw. Original QEMU 11.1.1-r2 exits with SIGABRT.
* At 13:00:06 and 13:02:49 UTC, QEMU executed a freed input callback during
  shutdown. QEMU 11.1 added input cleanup, but the installed spice-server
  cannot remove those interfaces: `VD_INTERFACE_REMOVING unsupported`.
  Keeping modifier/key state pressed while quitting a disposable 2D QXL
  guest reproduces SIGSEGV with the original binary.

QEMU package 11.1.1-r3 carries two focused patches:

* `0005-spice-defer-scanout-until-gl-draw-done.patch` tracks an outstanding
  draw and retains the latest scanout and monitor configuration until the
  real completion callback. Superseded/pending file descriptors are closed.
  The callback applies the deferred scanout before unblocking the renderer.
* `0006-spice-avoid-broken-input-cleanup.patch` keeps keyboard/mouse callback
  structures alive until server destruction, following the
  [official Proxmox workaround](https://git.proxmox.com/?p=pve-qemu.git;a=blob_plain;f=debian/patches/pve/0046-ui-spice-core-work-around-broken-input-cleanup-in-li.patch;hb=HEAD).

The QEMU build also explicitly disables its unrequested PipeWire backend.
Otherwise its automatic detection links against staged PipeWire without
the corresponding QEMU APK dependency and fails the package dependency check.
SPICE, VirtIO, VirGL, OpenGL and VNC remain enabled.

Render-node permissions were already correct (`root:render 0660`), and both
the physical host EGL probe and ordinary-user GTK GLArea used Intel hardware.
The normal desktop initially used pixman. Its renderer was saved as `gl`
without interrupting the existing session during diagnosis; the activation
follow-up below records the subsequent desktop restart.

## Validation

| Check | Result |
| --- | --- |
| Original binary: reset with unacknowledged GL draw | SIGABRT, original assertion reproduced |
| Original binary: quit with pressed input state | SIGSEGV, unsupported input removal reproduced |
| Installed r3: three resets with 500 ms delayed draw acknowledgements | Pass; QEMU alive throughout and exits 0 |
| Installed r3: pressed-input shutdown, GL and QXL | Pass; both exit 0 |
| Guest EGL shader on physical Intel host | Pass; `virgl (Mesa Intel(R) UHD Graphics (JSL))`, OpenGL ES 3.2, pixel `17,204,51,255` |
| Ordinary-user GTK/SPICE on separate Intel GL Weston | Pass; test pattern visibly displayed, disconnect/reconnect succeeds, QEMU exits 0 |
| Existing archlinux VM and desktop | Original PIDs retained; live VM XML unchanged |
| Router smoke checks | br-lan up, local HTTP 200, DNS lookup succeeds, procd/virtqemud active |
| QEMU package and complete systemd firmware builds | Pass |
| APK signature, target trust and image checksums | Pass |

The GUI test used a separate loopback VNC GL compositor, a UNIX SPICE socket
and a private 512 MiB KVM guest with no network. It did not alter the user's
VM, seize the normal desktop's DRM output, or expose a SPICE TCP listener.
The test VMs/compositor are stopped after validation.

The reset/shutdown tests still print spice-server surface teardown warnings
(`canvas ... NULL`, `double destroy of primary surface`). These warnings are
recorded; the tested processes exit normally. QXL is tested for 2D/input
cleanup, and its lack of an accelerated EGL result is not a 3D pass.

Reproduce with a compatible test kernel/initramfs containing a guest EGL
probe, target SpiceClientGLib GI and KVM access:

```sh
sudo python3 scripts/tests/spice-gl-reset.py \
  --kernel /path/to/bzImage --initrd /path/to/test-initramfs.cpio.gz \
  --video gl --resets 3 --duration 25
sudo python3 scripts/tests/spice-gl-reset.py \
  --kernel /path/to/bzImage --initrd /path/to/test-initramfs.cpio.gz \
  --video qxl --resets 0 --duration 4
```

The script creates a private disk and QEMU process, uses QMP only on that
process, and requires successful input connection, requested GL resets and
normal shutdown. It does not operate on existing libvirt domains.

## Artifacts and deployment state

* `bin/systemd/packages/x86_64/packages/qemu-x86_64-softmmu-11.1.1-r3.apk`
  SHA256: `8ac89e9c0c0c7b9a0f2214be4842d2b013f527d4e894c5094bd990e7b43ca66c`.
* `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`
  SHA256: `e88f2222610847fe2892ff85caa65f9214034fd083513fa9bdc1eb9e7c3a1b0e`.
* Independent feed changes are exported in
  `patches/feeds/0004-packages-spice-crash-fixes.patch`; its base is recorded
  in `configs/spice-crash-feeds.json`. Apply with `git -C feeds/packages apply
  ../../patches/feeds/0004-packages-spice-crash-fixes.patch` on that base.
  Do not reapply to the current feed, where these changes already exist.

Only the signed QEMU APK was upgraded on the physical host, using its native
trusted key. The old binary is retained in the host's
`/srv/libvirt/validation-backup/spice-20261012/`. No firmware was flashed and
the newly built complete image has not been cold-boot validated in this run.
Activating the updated binary requires a full guest stop/start; an in-guest
reboot does not replace QEMU. Changing the saved GL desktop renderer requires
a desktop restart. Both activation steps are completed in the follow-up below.

Private journal/build logs and test screenshots are held outside the source
tree in `/srv/openwrt-validation/spice-physical-crash-20261012/`. No credentials,
TLS keys or core dumps are included in this repair's source changes.
Unrelated local modifications are preserved. The QEMU fixes are committed in
the independent packages feed; the main tree records the exported patch,
feed revision, regression script and validation report. No changes are pushed.

## Activation follow-up (2026-10-12 22:18, Asia/Singapore)

On the user's subsequent instruction, the normal desktop session was
restarted with GL without rebooting the router. The archlinux VM was already
shut off and already configured for SPICE GL plus VirtIO 3D; it was started
without changing its XML. Its new QEMU process executable hash matches the
installed r3 binary. The ordinary-user virt-manager console was opened on
the new Wayland desktop; a VNC capture confirms the Arch Linux login prompt
is displayed through SPICE. Desktop, procd and virtqemud are active, and LAN
HTTP still responds with 200. The earlier pending activation described
above is now complete; `live-activation.log` records this follow-up.
