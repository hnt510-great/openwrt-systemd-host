# SPICE, VirtIO and OpenGL validation

This validation targets the x86_64/glibc native-systemd image. The build
adds SPICE, QEMU EGL/GBM and VirGL, spice-gtk 0.41 with GTK3/Wayland and
introspection, GLVND 1.7.0, and one Mesa provider containing Intel
iris/crocus/i915, virtual virgl and software softpipe. VNC remains enabled.
Existing CPU host-passthrough, VirtIO block and VirtIO network support is
retained. XML and command examples are in [libvirt.md](libvirt.md), and GUI
and permission instructions are in [virt-manager.md](virt-manager.md).

## Build evidence

Package builds and the complete firmware build are recorded under
`/srv/openwrt-validation/virtio-spice-validation-20261011/`. The initial runtime
attempt exposed the missing desktop OpenGL dispatch library required by
VirGL. The corrected build uses GLVND and Mesa's EGL vendor JSON instead of
substituting GLES or a build-host library.

Package builds include Mesa, spice-gtk, QEMU, libvirt and virt-manager. A
complete systemd firmware build follows those builds. The final dependency
closure contains 217 signed APKs, including the selected Mesa provider and
both SPICE GI namespaces. All EFI target checksums are verified with the
build's `sha256sums` file.

The runtime tests exposed and fixed three integration issues: missing desktop
OpenGL dispatch (GLVND), the first SPICE GL frame arriving before monitor
configuration (spice-gtk now queues a render when ready), and DRM hotplug
node creation leaving render permissions at 0600 and the desktop rule
assigning them to the video group. Wayland's rule now handles display cards
only, and libvirt applies a final render-node
rule after node creation. Both startup and actual virtual GPU unbind/rebind
are checked; changing permissions manually alone is insufficient.

The final EFI image is:

`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA256:

`ba274efbe94434d0b4fce21d5a69d77d09f88ebaf8a4ffa20c9f57f4fa7bab7c`

The final full build log is `firmware-build5.log`; signed APKs are frozen in
`application-apks/` with hashes in `application-artifact-manifest.json` and
signature results in `application-signatures.log`.

## Runtime evidence

The graphical acceptance run used an ordinary `vmadmin` account explicitly
authorized through `virt-manager-setup`. The manager and SPICE GTK client ran
under that UID. The retained GPU results describe that dated test environment;
current host-session setup is documented in [GNOME](gnome-desktop.md).

| Check | Observed result |
| --- | --- |
| CPU/KVM | `host-passthrough` in domcapabilities and created XML; QMP reports KVM enabled/present |
| Disk/network | VirtIO block writes/readback; guests obtain OpenWrt DHCP leases on `br-lan`; HTTP traffic survives network/firewall reload |
| GUI new guest | Ordinary user imports a Linux disk and boots SPICE + VirtIO video with 3D off; VirtIO disk/NIC and host-passthrough CPU are saved |
| GUI manual 3D | Video acceleration and SPICE GL/renderD128 selections save `accel3d='yes'`, `gl enable='yes'`, and Listen None; the guest boots |
| Accelerated rendering | Nested GBM/EGL shader plus FBO/readback returns RGBA `17,204,51,255`; renderer is `virgl (virgl (AMD Radeon RX 6600 XT ...))`, OpenGL ES 3.2 Mesa 26.2.2 |
| SPICE display/input | First connection displays a DRM scanout pattern without resizing; reconnect, keyboard events and absolute mouse/button events reach the guest |
| VNC | Existing loopback VNC guest displays the same pattern and receives keyboard/pointer events |
| No GPU | Default 2D SPICE guest starts; explicit GL fails with `Path '/dev/dri/renderD128' is not accessible: No such file or directory` |
| Authorization | Unauthorized and revoked users get socket Permission denied; helper-added render membership is removed, pre-existing membership retained |
| Device permissions | Display card stays root:video 0660; render node is root:render 0660 after startup and GPU hotplug; libvirt-qemu can open it |
| Persistence | Reboot retains domain definitions, user/group authorization, desktop GL selection and dconf setting; 2D guest autostart succeeds |
| Recovery | GRUB procd recovery actually runs procd as PID 1; LAN, DNS, SSH and LuCI login page work; definitions/disks/dconf persist and libvirt guests remain stopped; returning to native systemd restores autostart |

The created XML has no sound device or USB redirection device. Existing
explicit VNC/VGA/SATA choices pass the read-only runtime smoke check. The
read-only script is `scripts/tests/virtio-spice-smoke.py`, and the accelerated
rendering probe source is `scripts/tests/virtio-egl-probe.c`. Guest test
initramfs libraries come from target package outputs, never host libraries.

The GUI creation/manual-3D acceptance run uses the preceding complete image.
The final image changes only libvirt's render hotplug rule and Wayland's
card-node rule. `gui-package-identity.log` confirms that virt-manager,
spice-gtk, QEMU, Mesa, openwrt-desktop and dconf APK hashes are unchanged.
The final image is cold-booted on fresh disks, with no replacement scripts;
GPU hotplug, GI/default checks, nested accelerated rendering, real client
exit/reconnect, authorization/revoke, networking and persistence are repeated.

Logs and screenshots live in the validation directory named above, including
`final-runtime-smoke.log`, `final-spice-gl-runtime.log`,
`final-gui-created.xml`, `final-gui-gl-saved.xml`, `final-auth-permissions.log`,
`post-reboot.log`, `procd-recovery-services.log` and the `no-gpu` directory.
Final-image evidence includes `image5-runtime-smoke-hotplug.log`,
`image5-gl-desktop.log`, `image5-nested-gl.log`, `image5-spice-gl-reconnect.png`,
`image5-network.log`, `image5-auth-pre-reboot.log`, `image5-post-reboot.log`,
`image5-disk-after.log`, `image5-procd-recovery.log` and
`no-gpu/image5-no-gpu.log`. A unique marker written at disk offset 2 MiB
is read back in full after reboot, independently of the guest's boot marker.
Recovery also checks `sysupgrade -T` without flashing.

The LuCI unauthenticated page uses HTTP 403 with a working login form; this
is not a listener failure. Existing firewall warnings about disabled
Passwall includes and GTK locale/plugin-loader warnings are recorded.


## Cleanup and source checks

All nested test guests are gracefully shut down before powering off the
outer VM. Both final outer VM processes have exited, and the VNC UI clients
are closed. `final-cleanup.log` and `image5-return-and-shutdown.log` record
this. Pre-existing system/session libvirt domain states exactly match the
baseline (`win2k22` and `debian12` remain running; earlier OpenWrt test domains
remain shut off). Unrelated baseline source hashes are preserved. Shell and
Python syntax checks and main/feed whitespace checks pass. Validation itself
performs no source commit or push; subsequent scoped commits save the
implementation and feed patches.

## Test boundaries

Tests use a disposable outer UEFI/KVM VM with VirtIO-GPU GL backed by the
build host's AMD RX 6600 XT. The firmware contains only Intel and virtual GPU
Mesa drivers. A nested renderer backed by that GPU is evidence for the
virtual GPU path; it does not certify physical Intel graphics. Software
renderers do not satisfy acceleration acceptance.

Test accounts, SSH keys, WAN DHCP and DHCP isolation rules exist only in the
disposable VM overlay. No physical device is flashed or remote push performed.
Pre-existing host domains and unrelated changes are preserved. No AMD target drivers, PCI passthrough, Vulkan or externally
listening SPICE server are added.
