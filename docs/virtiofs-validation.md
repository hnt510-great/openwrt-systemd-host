# Libvirt virtio-fs validation

Validated on 2026-11-12 for x86_64/glibc native-systemd OpenWrt. Guide:
[libvirt.md](libvirt.md#sharing-host-directories-virtio-fs).

## Image and packages

| Item | Value |
|---|---|
| Image | `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz` |
| SHA256 | `b0e1066138e6245a29b77001ee3aaf97c3a4c4593f430d2fb069d8138e309963` |
| Build | `python3 scripts/build-and-publish.py build-only -j12`, kernel sequence 62 (new generation: `CONFIG_VIRTIO_FS=m`) |
| Kernel | `linux-image-7.3.4-62-openwrt 7.3.4-r62`; `kmod-fs-virtiofs 1000.62.7.3.4-r1` (SHA256 `866a5651e798d514188fca5432295e7e29acec23f3b5c04d16c762e987fc25ec`) |
| Packages | `virtiofsd 1.14.0-r1` (SHA256 `883dff9c525d8703f26c8021fa970b5b9b62bdb1b3d401a6114f6ca73fe54edf`), `libvirt-daemon 12.9.0-r3` (SHA256 `e917ceaba0516ac6953c363ddd20975ba76f0edb34e48b2966f95163ba116fdb`), `base-files 1759.14`, QEMU `11.1.3-r2` (unchanged) |

Build checks: the Cargo vendor tarball
`virtiofsd-1.14.0-vendor.tar.zst` was generated twice from the GitLab
`v1.14.0` archive with identical SHA256
(`12ec4bb117c743d6891c74bb774200ed8df408f636fb90e683c43aa675505af0`).
The binary links `libseccomp.so.2`, `libcap-ng.so.0`, `libgcc_s.so.1` and
`libc.so.6`, and the ELF ABI inventory declares the same `so:` dependencies.
The QEMU build already enables `vhost_user` and `CONFIG_VHOST_USER_FS`. Libvirt
reads vhost-user descriptors from `QEMU_DATADIR` (`/usr/share/qemu`). The
kernel build has `CONFIG_FUSE_FS=m` and `CONFIG_VIRTIO_FS=m` and produces
`fs/fuse/virtiofs.ko`; virtio and virtio-pci remain built in on x86/64.
`scripts/update-custom-packages.py --check --package virtiofsd` reports
`local`, `scripts/tests/test-custom-package-updates.py` passes (47 tests) and
`git diff --check` passes.

The first generation-62 build failed in `openssh` (with-pam). Its compile log
ended without an error, and rebuilding the package alone with `-j1 V=s`
succeeded. The repeated `build-only` reused sequence 62 and succeeded with
unchanged inputs.

## Host smoke test

The target-built binary was run as root with the target glibc loader on the
build host, using `--sandbox=namespace --seccomp=kill`. A host QEMU KVM guest
(Debian kernel 7.2.15, memfd shared memory, `vhost-user-fs-pci`) mounted the
tag, read a host file, wrote a file and created a directory (both root-owned
on the host), then unmounted. virtiofsd exited 0 when the guest disconnected,
with no seccomp kills.

## OpenWrt as a virtio-fs guest

The exact image boots as a disposable KVM guest of the build host (UEFI,
2 GiB memfd shared memory, `vhost-user-fs-pci` tag `shared`). The host side is
the target-built virtiofsd (run as root with the target glibc loader,
`--sandbox=namespace --seccomp=kill`), started once per boot. Personal
Passwall/WAN integrations are disabled as in `scripts/test-image-network.py`.

| Check | Result |
|---|---|
| Kernel package | Pass: `kmod-fs-virtiofs` and `kmod-fuse` installed; `/lib/modules/7.3.4-62-openwrt/virtiofs.ko` |
| Device bound at boot | Pass: virtio device `0x001a` bound to the `virtiofs` driver without a manual `modprobe` |
| Module loaded | Pass: `virtiofs` in `/proc/filesystems`; `virtiofs` and `fuse` in `lsmod` |
| `mount -t virtiofs shared /mnt/host` | Pass: reads the host file, writes a file and creates a directory; the host sees the file and a root-owned directory |
| systemd mount unit | Pass: the documented `mnt-host.mount` starts |
| Configuration backup | Pass: `sysupgrade -l` lists `/etc/systemd/system/mnt-host.mount` |
| After reboot | Pass: `mnt-host.mount` is active and shows a file the host created while the guest was off |
| Kernel log | Pass: only fuse/virtio-fs initialization messages; no errors |
| virtiofsd | Pass: exits 0 after each guest shutdown |

## Libvirt host checks (nested VM)

The same image boots as a disposable L1 KVM guest (UEFI, 4 GiB). Inside it,
libvirt runs L2 fixture guests with a busybox initramfs and the build host's
Debian kernel (`7.2.15+deb14-amd64`, virtio-fs built in). The guests mount
the share, print results to a file-backed serial console and power off.

| Check | Result |
|---|---|
| Packages | Pass: `virtiofsd-1.14.0-r1` and `libvirt-daemon-12.9.0-r3` installed; `virtiofsd --version` is 1.14.0 |
| Descriptor | Pass: `/usr/share/qemu/vhost-user/50-virtiofsd.json` points to `/usr/libexec/virtiofsd` |
| Domain capabilities | Pass: `<filesystem supported='yes'>` with driver types `path` and `virtiofs` |
| `/srv/libvirt/shares` | Pass: created by `libvirt-openwrt-prepare`, 0755 root:root |
| Packaged example | Pass: `openwrt-virtiofs-vm.xml` defines with memfd/shared backing and the virtiofs filesystem, then undefines |
| Read-write share | Pass: the guest mounts tag `shared`, reads the host file, writes a file and creates a directory; the host sees `guest-rw` and a root-owned directory |
| virtiofsd process | Pass: runs as root, `/usr/libexec/virtiofsd --fd=23 --shared-dir /srv/libvirt/shares/fixture-rw` (sandbox parent and child) |
| virtiofsd log | Pass: `/var/log/libvirt/qemu/fixture-vfs-rw-fs0-virtiofsd.log` |
| `systemctl restart virtqemud` with the guest running | Pass: the guest stays running, the same virtiofsd processes remain, and the guest then reads a newly created host file and writes its reply |
| Guest shutdown | Pass: clean unmount; no virtiofsd process remains after the guest stops |
| `<readonly/>` share | Pass: the guest reads the host file; the write is refused and nothing appears on the host |
| Seccomp | Pass: no kernel log lines for virtiofsd or seccomp audit (`type=1326`) |

virtiofsd logs a warning that the L1 overlay root does not support file
handles and falls back to `O_PATH` file descriptors. This is expected on
OpenWrt's overlay root and did not affect any check.

## Failed harness runs

The product was unchanged between these runs; only the harness scripts were
corrected. On the earlier sequence-61 image (without the guest driver), run 1
copied `lost+found` from the fixture disk. Run 2's seccomp grep matched
systemd's `+SECCOMP` boot banner, although every functional check had passed.
Run 3's pipeline exit status aborted the `sh -e` command. Run 4 passed all 15
checks on that image. On the final image, the first guest run expected the
driver name `virtio_fs` (it is `virtiofs`). It also read a guest-created file,
root-owned 0600 because of the harness shell's `umask 077`, without sudo. An
earlier attempt ran out of host disk space while copying the image; the
harnesses now delete their raw image copies and overlays when they finish.

## Publication

Published on 2026-11-12 with `scripts/publish-changed-feeds.sh` after a
passing `--dry-run`, from the committed tree rebuilt with
`build-and-publish.py build-only` (kernel sequence 62 reused; base-files
`1760.14` after the commit count changed). The router upgrade simulation
against the installed router passed with no blockers and 264 package changes,
mostly kernel generation 61 to 62. Userspace snapshot:
`/srv/openwrt-feeds/public/snapshots/20261112T110343.841044Z`; kernel
snapshot: `/srv/openwrt-feeds/public/kernel-snapshots/1794481464331660230`.
Nothing was installed on the router.

## Scope

This was KVM and nested AMD KVM validation on the build host. No physical
device was flashed and nothing was installed on the router. Windows guests (viofs/WinFsp), virt-manager's GUI filesystem dialog,
live migration, DAX and `accessmode='mapped'`/ID mapping were not tested. An
OpenWrt guest running under libvirt on an OpenWrt host (as opposed to under
plain QEMU on the build host) was not run end to end.

## Evidence

`/srv/openwrt-validation/virtiofs-validation-20261112/`:
- harnesses: `run-guest-test.py`, `run-vm-test.py`, `build-fixture.sh`, `init` and `domains/{rw,ro}.xml`;
- guest-side run `guest2/` (`receipt.json` with all 9 checks, virtiofsd SHA256 `057305712f26be32290c7dfff16a4f8f6eb19352d5ad49814990deb20a5dd5a8`, serial/command logs, `virtiofsd-{1,2}.log`);
- host-side run `run5/` (`receipt.json` with all 15 checks, fixture SHA256 `5836d27a3700fc51933921c3a52f6c8cdb70ecce07772efe1e49a5a86c4aedd3`);
- `host-smoke/`, `image-build.log` (sequence 61) and `image-build-gen62.log`;
- failed runs `run1-failed-harness`, `run2-failed-assertion`, `run3-failed-harness`, the passing sequence-61 run `run4`, and `guest1-failed-harness`.
