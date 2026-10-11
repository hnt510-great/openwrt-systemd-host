# Libvirt integration validation, 2026-10-11

The x86_64/glibc native-systemd firmware and all three libvirt 12.8.0 APKs
were built successfully. The final firmware was cold-booted under an isolated
UEFI/KVM VM with two restricted user-network NICs and tested with a nested
guest. The validation VM used test-only SSH authentication in its writable
overlay; firmware contains no preseeded human accounts or SSH keys.

## Delivered artifacts

Firmware, relative to the build tree:

    bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz

Size: 335804453 bytes. SHA256:

    2f0eeb2614313e46fe5d6d75813015e975b41039d292c0aa7c960bb2d5f3c6d4

Matching signed packages in `bin/systemd/packages/x86_64/base`:

| Package | SHA256 |
| --- | --- |
| libvirt-12.8.0-r1.apk | a0c0cddcd2145d9142df2d85c067ff51ff6f5240091ea2c41ef63bb8e8582546 |
| libvirt-daemon-12.8.0-r1.apk | 4385fb9bd933b1e0f13e2cbdfabe9fbd7862a2766212c5efa7a6902cf311e615 |
| virsh-12.8.0-r1.apk | ef6b2bdc381772acf080565eae7fcd86989139c508b65b820f97226a4ff2a164 |

Source XML: `package/custom/libvirt/files/openwrt-vm.xml`. The package installs
it at `/usr/share/libvirt/examples/openwrt-vm.xml`. Usage and backup guidance:
[libvirt.md](libvirt.md).

## Build and configuration checks

- Package compilation and the complete firmware build passed. Final full
  build used `make -j4 V=s`, with a 4 GiB memory limit on the build scope.
- All final target artifact checksums passed `sha256sum -c sha256sums`.
- Original enabled configuration entries were retained. Added package
  selections: libvirt, virsh, libvirt-daemon, libtirpc and kvm-support.
- Host libxml2 now supplies xmllint. Target libraries come from staging;
  installed library dependencies, daemon drivers and APK metadata were checked.
- Added kernel KVM_AMD and KVM_IOAPIC. A real nested KVM start initially
  exposed the missing IOAPIC option; the final kernel resolves that failure.
- Shell syntax, example XML schema, patch style and whitespace checks passed.

## Final firmware runtime results

| Check | Result |
| --- | --- |
| Native boot | PID 1 systemd; router services active; no failed systemd units |
| Client and API | virsh 12.8.0, QEMU API 12.8.0, hypervisor QEMU 11.1.1 |
| Capabilities | Both qemu and kvm domain types present |
| Service ordering | Persistent bind mount precedes daemons; runtime unit verification passed |
| Access control | Root-owned mode-0600 sockets; nobody denied qemu:///system access |
| QEMU identity | UID/GID 191, locked non-login account; KVM device root:kvm mode 0660 |
| KVM execution | Actual nested guest boot; QMP query-kvm enabled=true, present=true |
| TCG execution | Final image also booted the test guest with KVM disabled; HTTP and ACPI shutdown passed |
| Cgroups | QEMU emulator placed in its delegated /machine/...libvirt-qemu cgroup |
| Storage | Directory pool, 4 GiB qcow2 volume, domain XML define/start/list passed |
| Console and shutdown | Serial console commands and guest ACPI shutdown passed |
| Network | Guest obtained an OpenWrt DHCP lease on br-lan; ping and HTTP passed |
| Network reload | Guest HTTP remained reachable after netifd reload and firewall4 reload |
| Host reboot | Running guest shut down cleanly; domain and pool autostart restored |
| Persistence | Domain/pool definitions, state marker, disk marker, secret key and secret value survived reboot |
| APK transaction | All three signatures verified; forced reinstall passed and preserved edited qemu.conf |
| Upgrade backup | sysupgrade -l included domain/pool XML and autostart configuration |
| Recovery | Actual GRUB procd recovery boot retained definitions without starting libvirt or guests; native boot restored |

The test disk was written by the inner guest, then inspected after shutdown
and host reboot using a sparse raw conversion. Its marker at byte 1048576
matched `libvirt-disk-persistence-check`. The secret test checked the key's
checksum and retrieved the same saved value after reboot, without putting
the generated key into documentation or firmware.

The repository script `scripts/tests/libvirt-guest-smoke.sh` checks the native
services, client/capabilities, identities, sockets, bind mount, LAN status,
backup selection and absence of libvirt network/proxy daemons. It passed on
the final image. The additional nested-guest fixture uses this firmware's
kernel and a small test initramfs to make console, DHCP, ACPI shutdown and
disk writes reproducible; it is separate from the shipped XML example.

## Environment and limits

This was nested AMD KVM validation, not a physical-router deployment or an
Intel hardware test. No real PPPoE, upstream WAN, external disk or device
passthrough was tested. Both KVM and TCG execution were confirmed on the
final firmware, with separate QMP accelerator checks.

The outer QEMU user-network backend has its own DHCP responder. To isolate
the OpenWrt DHCP check, the disposable router VM forced its LAN DHCP service
and temporarily filtered competing DHCP replies arriving on eth0. Those test
settings were never added to the source overlay or firmware. The guest then
received 192.0.2.185 from OpenWrt, and communicated through br-lan before
and after router/firewall reloads.

Existing firewall configuration emitted fullcone/passwall compatibility
warnings during reload; guest traffic still passed. The package does not
add libvirt NAT/firewall rules. There is no AppArmor/SELinux confinement or
private QEMU device namespace in this integration; DAC, disk locking and
cgroups remain enabled. Large disks require separately provisioned storage.

Full raw logs, build backups and disposable VM fixtures are retained under
`/srv/openwrt-validation/libvirt-validation-20261011/`. Key logs include
`image-kvm-final.log`, `package-build-final.log`, `guest-smoke-final.log`,
`guest-kvm-console.log`, `guest-kvm-network.log`,
`guest-reboot-persistence.log`, `guest-disk-persistence.log`,
`guest-apk-reinstall-final.log`, `guest-final-network-recovery.log` and
`guest-procd-recovery.log`, plus `guest-final-tcg.log`, in its `logs` directory.

The disposable inner guest and outer validation VM were shut down after
testing. The two pre-existing user-session OpenWrt VMs remain shut off.
