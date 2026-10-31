# Full image build, VM validation and publication, 2026-10-31

Built the complete x86/64 glibc native-systemd GNOME firmware after the
2026-10-31 main/feed synchronization (see the
[patch review](mainline-kernel-patch-review.md)). It includes Linux 7.3.1, the
ported Rust OPP/ax88796b patches and 7.3 configuration defaults, PPP 2.5.4-r7,
libostree 2026.6, tpm2-tss 4.2.1 and wireplumber 0.5.19. The build used
`scripts/build-and-publish.py build-only -j8 V=s` and exited successfully.

`.config` was normalized with `make defconfig` first. It gained only the new
unset `RUST_TOOLCHAINOPTS`, `RUST_SCCACHE` (moved) and `kmod-seg-led-gpio`
entries; the original is kept as `config.before` in the evidence directory.

## Exact artifact

- Release: `7.3.1-owrt-2a97e7c5ca6a8af1585dd0410625ea73-r1-g42`.
- EFI image: `openwrt-x86-64-generic-squashfs-combined-efi.img.gz` (711437945 bytes).
- SHA256: `2fee3574e9f975e96ba2c522a59f4bb098ba4a5b0476bf71ad26acfb431389f9`.
- Revision: `r37939+211-a516fe3151`.

## VM acceptance

The exact compressed image was booted through fresh qcow2 overlays with
private UEFI state and isolated QEMU networks. All test VMs were stopped.

| Check | Result |
| --- | --- |
| Two-VM gate: native init, router services, WAN/LAN DHCP, DNS, routing/NAT, LuCI HTTP/auth, ubus board | Passed (9/9) on kernel 7.3.1 g42 |
| Native systemd boot, `is-system-running`, failed units | `running`, no failed units |
| Installed versions | kernel 7.3.1 g42, ppp r7, libostree 2026.6, tpm2-tss 4.2.1, wireplumber 0.5.19, spice-gtk r2, libvirt r10 |
| PPP `REQPREFIX`/`IP6TABLE` quoting and reqprefix warning | Present in `/lib/netifd/proto/ppp.sh` |
| wireplumber runtime | Compiled and linked with 0.5.19 |
| kernelctl state, module index (`depmod -n`) | Passed; only expected VM probe/fstab messages |
| `test-libvirt-secondary-drivers.py` | Passed (2 tests) |
| `virtio-spice-smoke.py` (GL scanout default, SPICE/VirtIO defaults, render node) | Passed after test correction below |
| Guest reboot | Returned to `running` on g42 |

`virtio-spice-smoke.py` still asserted that new SPICE guests get no sound card.
Since `c087d41de7` the virt-manager patch intentionally adds one, as
documented in [libvirt](libvirt.md); the assertion was corrected. This firmware
has no 9p transport, so the test scripts were copied over the serial console
and checked by SHA256.

The scope excludes GPU passthrough and physical peripherals, a real graphical
desktop, RDP or SPICE client sessions, PPPoE links, a compiled Rust kernel and
physical-router acceptance.

## Publication

- Userspace: `/srv/openwrt-feeds/public/snapshots/20261031T053831.606039Z`;
  new ABI tree `7.3.1~2a97e7c5ca6a8af1585dd0410625ea73-r1`, 1242 packages,
  `same_version_rebuilds=[]`.
- Kernel: `/srv/openwrt-feeds/public/kernel-snapshots/1793425169197694275`;
  1037 packages, 2 retained image generations.
- Signed-package, ELF/ABI and router upgrade preflight with both solver
  simulations passed against the router baseline (g40) before promotion.
  Receipt `upgrade-receipts/1793425247359825671.json`. Nothing was installed
  on the router and it was not rebooted.

Evidence: `bin/validation/sync-20261031/` (build and publication logs, image,
manifest, VM receipts and serial logs).
