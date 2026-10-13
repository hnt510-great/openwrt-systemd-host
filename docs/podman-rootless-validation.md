# Podman rootless validation, 2026-10-13

The local x86_64/glibc native-systemd image was rebuilt and cold-boot tested
before installing the repair on the physical router at `192.0.2.1`.
The router was not flashed or rebooted.

| Package | Version |
| --- | --- |
| podman | 5.8.4-r4 |
| crun | 1.28-r2 |
| shadow-newuidmap | 4.20.2-r1 |
| shadow-newgidmap | 4.20.2-r1 |
| openwrt-podman-rootless | 1 |

Narrow package builds and the complete `make -j4 V=s` build passed.
The image manifest includes all five versions. Both UID/GID helpers are
root-owned, mode 4755, and use the glibc dynamic loader. Crun reports
`+SYSTEMD`; procd builds retain its previous systemd-disabled configuration.
Podman uses systemd cgroups in native images and no longer forces user
runtime/network data into root-owned paths.

Image:
`bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz`

SHA256:
`27f97f799937d4e8a4b014b6fcfd3394cf2666070adc4eb938968ac223e87fad`

This hash exactly matches the cold-boot-tested artifact. Published checksum
verification passed for every artifact. The full image's SquashFS contains
the setuid helpers and enabled TUN-permission boot service. Both validation
VMs were shut down after testing.

## VM results

Fresh boot created the personal account's subordinate UID/GID assignments
and `podman` group membership. `/dev/net/tun` was `root:podman`, mode 0660.
Repeated enrollment preserved the mappings byte-for-byte. A separate account
with no existing mappings received nonoverlapping UID/GID ranges.

`scripts/test-podman-rootless.sh` passed before and after a VM reboot:
default rootless container startup, 65536 subordinate IDs in both namespaces,
chown to container UID 1234/GID 2345, DNS resolution and HTTPS access.
It used normal crun, networking and cgroup settings, without the previous
host-network, disabled-cgroup or single-ID workarounds. Rootful startup with
the default bridge also passed DNS and HTTPS tests in the VM. The booted
system reported no failed systemd units.

The VM's WAN was adapted from the source's physical PPPoE setup to QEMU
DHCP, and PassWall was stopped/disabled only inside the disposable VM.
Neither adaptation changed the source overlay or physical router.

## Physical-router results

The router's existing trusted public key verified all five APKs. Offline
installation simulation contained exactly the five listed changes and
retained existing dependencies. Installed Podman, crun and UID/GID helper
hashes match the signed package payloads.

Account `desktop-user` was enrolled with these host ranges:

```text
subuid: desktop-user:100000:65536
subgid: desktop-user:165536:65536
```

The account retained its previous supplementary groups and gained `podman`.
`podman system migrate` restarted the previously cached single-ID namespace;
no container/image/volume reset was performed. A newly authenticated SSH
connection was necessary to refresh supplementary groups. The smoke test
passed from that session with no sudo or container-setting overrides.
`podman ps` succeeded, and interactive zsh retained `docker=podman`.
All test containers were removed by `--rm`; the Alpine test image remains
cached for reuse.

The TUN boot service is enabled. The existing physical tmpfiles workaround
was updated to the same `root:podman`, mode 0660 policy. Package installation
had already consumed the support package's first-boot script; setup continued
with explicit account enrollment. The old Podman UCI-default whiteout was
preserved, and the new `.apk-new` copy was archived away from boot scripts
before temporary installer cleanup. Upstream firewall defaults were not
rerun.

Before/after hashes of `/etc/config/firewall`, `/etc/config/passwall`,
`/etc/config/network` and `/etc/config/dhcp` are identical. The router's boot
ID is unchanged, LAN stayed up, the PPPoE default route remained present,
and host DNS/HTTPS tests passed. Procd and router services remained active;
the `fw4` and `passwall` nftables tables remained present.

Physical reboot persistence is untested because the router supplies the
Internet connection. TUN permissions and default startup survived a VM
reboot. Rootful bridge networking was tested only in the VM; physical
rootful networking and actual PassWall proxy routing remain unverified.
The rebuilt firmware has not been flashed to physical hardware.

Private build/test logs and the pre-install configuration backup are under
`/srv/openwrt-validation/podman-validation-20261013/`. Temporary installer files
were removed from the router. Unrelated local work was preserved; nothing
was committed or pushed. The existing unrelated WeeChat Kconfig recursion
warning remains; the required package selections were checked explicitly.
