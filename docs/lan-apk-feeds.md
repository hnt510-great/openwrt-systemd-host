# Local LAN APK feeds

The Debian build host serves signed native-systemd/glibc packages at
`http://192.0.2.164:8088`. Its system service is `lan-apk-feeds.service` and
starts automatically at boot. The `lan-apk-feeds` package selects all nine
repositories, including `custom`,
in `/etc/apk/repositories.d/lan-local.list` from the installed kernel APK version.
It regenerates this file at boot and after APK transactions, including after
sysupgrade restores an older list. It preserves unrelated custom repositories.

The feed URL contains the exact installed kernel package version:

```text
http://192.0.2.164:8088/abi/6.18.55~ef561c78a2b577ae422f9289311ff293-r1/target/packages.adb
```

The other feeds are `base`, `luci`, `packages`, `passwall_luci`,
`passwall_packages`, `taskplan`, `video`, and `custom`. Only locally built packages are
available; this is not a mirror of every upstream package.

On the router, use:

```sh
sudo apk update
sudo apk add --simulate PACKAGE
sudo apk add PACKAGE
```

`apk update` refreshes indexes; it does not upgrade installed packages.

For targeted `base-files` upgrades and handling protected configuration files,
see [the base-files upgrade guide](base-files-upgrade.md).

For target-native application builds, `native-build-deps` selects the library
headers, pkg-config metadata and build tools, including the Cockpit dependency
stack. `cockpit-runtime-deps` keeps the runtime dependencies of a source-installed
Cockpit in APK world. Build and publish these packages before adding them on the
device; see [native development and migration](native-development.md#原生应用依赖与-cockpit).

The router already pins
`kernel=6.18.55~ef561c78a2b577ae422f9289311ff293-r1` in `/etc/apk/world`.
Keep that constraint. Existing upstream snapshot URLs remain commented out
because this firmware needs its matching native-systemd/glibc builds.

## Publish newly built packages

Run on the build host, from this checkout, after the package build completes:

```sh
./scripts/publish-changed-feeds.sh
```

Then run `sudo apk update` on the router. To combine building and publishing,
use this instead of a separate `make` and publisher invocation:

```sh
./scripts/build-and-publish.sh -j16 V=s
```

Make arguments are forwarded unchanged; package compilation targets also work.
Publication runs only after make succeeds. Ordinary `make` keeps its existing
behavior. Source APKs and indexes under `bin/` are not modified.

When `CONFIG_OPENWRT_KERNEL_UPGRADE=y`, this command also publishes the protected
kernel channel. Full/default builds reuse the sequence and kernel timestamp for
unchanged kernel inputs. Pure userspace changes therefore keep the existing
kernel generation. Relevant kernel/module/config/toolchain changes automatically
reserve a new publication sequence in `.config` and rebuild matching modules,
even if the ABI hash stays the same. Missing local input history conservatively
reserves a new generation. Both feed types pass signature, generation, completeness and
immutability preflight before publication. Userspace views are published first;
the kernel channel is exposed last. Existing ABI-local kernel packages and old
generations are limited to the two newest publication sequences in the kernel
channel, including their matching kmods, headers and trackers. Obsolete kernel
snapshots are deleted after the signed channel switches successfully. ABI-local
feeds remain unchanged. Stale build outputs are filtered rather than deleted.
See [the kernel upgrade guide](kernel-upgrade.md#build-and-publish).

In this mode, `publish-changed-feeds.sh` also handles both feed types, without
advancing the sequence. Package-only builds require a completed matching kernel
generation; kernel/module changes should use a full build so the sequence advances
when needed. Unchanged inputs also reuse the same sequence after a failed build.
There is no router installation or reboot in either wrapper. The following
ABI-specific details also describe the original behavior with the feature off.

The wrapper uses `configs/lan-apk-feeds.json` for the destination and LAN URL.
It detects the ABI from the completed build's `kernel.version` and cross-checks
the kernel APK metadata when present. With no metadata file, it reads the
single built kernel APK. Missing or inconsistent build metadata is rejected.
The config no longer pins the publisher to one router ABI. It invokes the
Python publisher
with `--incremental`. It hashes every current APK in `bin/systemd`, copies
only new/changed APKs, and signs indexes only for affected repositories.
Changes to custom package APKs update their source repository and the
projected `custom` repository together. Unchanged packages and indexes are
reused through hard links to retained snapshots; replacements always use
new inodes so older snapshots remain unchanged.

Previously published APKs are retained when a package clean removes their
build output. With no changes, the command reports `"status": "unchanged"`
and creates no snapshot. The first run against an older publication may
create a metadata-only snapshot to initialize the APK hash inventory.

To preview changes, including signature and ABI validation, use:

```sh
./scripts/publish-changed-feeds.sh --dry-run
```

To publish immediately after a successful package build:

```sh
make package/custom/openwrt-desktop/compile V=s &&
  ./scripts/publish-changed-feeds.sh
```

The same command works after a full successful firmware build with a new
ABI; no shell variable or `--kernel` is needed. Run the standalone publisher
after the build finishes. If an APK changes while it is copied, publication
fails before switching the active feed. `--kernel` (or a deliberately added
`config.kernel`) remains available to explicitly pin a publication. CLI
arguments override JSON defaults. Each ABI keeps its separate snapshot alias.

Output lists `changed_packages`, `affected_repositories`, and
`same_version_rebuilds`. Increase a package's `PKG_VERSION` or `PKG_RELEASE`
for reliable upgrade detection. A same-version content change is published
and reported but may require an explicit reinstall on the router. The
publisher does not change package versions, connect to the router, or install
updates there.

ucode interpreters, libraries and native consumers have a stricter rule:
same-version content changes are rejected and require a release bump. APK
packaging records a shared `ucode-abi` dependency for embedded runtimes and C
modules; publication checks the newest candidates, including retained packages,
against the interpreter provider before switching the feed. This prevents a
new module set from being published with an old netifd/rpcd runtime. See the
[ucode ABI repair and deployment record](ucode-abi-repair.md) for the mechanism,
tests, migration scope and physical-router results.

New/changed APKs are verified using `public-key.pem`; affected indexes are
signed using `private-key.pem`. Architecture and every direct kernel
dependency are checked, and the kernel package must match the configured
ABI. Wrong signatures, mismatched ABIs, conflicting custom copies, changes
to previously published kernel-dependent files, and signing-key changes
are rejected before switching the active feed.

The previous full publication mode remains available:

```sh
python3 scripts/publish-lan-apk-feeds.py --config configs/lan-apk-feeds.json
```

Full mode uses the current build outputs as the complete package set. It
retains the kernel-file preservation checks, so review errors before trying
to remove any published kernel-dependent package. This low-level command is for
the legacy ABI-specific workflow; use the combined wrappers when kernel upgrades
are enabled.

Snapshots live in `/srv/openwrt-feeds/public/snapshots/`. Each successful
publication atomically switches `/srv/openwrt-feeds/public/abi/KERNEL` to the
new snapshot. Older snapshots remain available for rollback. The manifest
records package counts, index hashes, signing-key hash, and hashes of
kernel-dependent APKs. It also records all APK file hashes for incremental
comparisons. The first snapshot is `20261014T032556.250223Z`.

## Custom source and APK feed

`feeds.conf.default` registers the existing local package sources:

```text
src-link custom ../package/custom
```

The relative link target is resolved from `feeds/`, so `feeds/custom` points
at this checkout's `package/custom`. Refresh its source index with:

```sh
./scripts/feeds update custom
```

These sources are already part of this build under `package/custom`; no
additional installation links or forced overrides are needed here. Build a
package using its existing path, for example:

```sh
make package/custom/openwrt-desktop/compile V=s
```

Then run the publisher command above and `sudo apk update` on the router.
The publisher automatically includes built APKs whose signed origin starts
with `feeds/base/custom/`, `package/custom/`, or `feeds/custom/`. It collects
all split packages, regenerates a signed `custom/packages.adb`, and verifies
signatures and kernel dependencies. Existing base/feed copies are retained;
conflicting APKs with the same filename are rejected. Source registration
and the router's binary repository serve different purposes; see
[OpenWrt feeds](https://openwrt.org/docs/guide-developer/feeds).

The router's custom feed URL is:

```text
http://192.0.2.164:8088/abi/6.18.55~ef561c78a2b577ae422f9289311ff293-r1/custom/packages.adb
```

On 2026-10-14 the source index contained 72 source definitions and 80 binary
package definitions; 76 built custom APKs were available. The physical
router refreshed all nine feeds, downloaded `openwrt-desktop` using only the
custom repository, verified its signature with existing keys, and completed
a simulated add without installing packages. Its world, package inventory,
kernel, boot ID, network, firewall, and DHCP state were unchanged.
`customfeeds.list` is included in the router's sysupgrade backup. The original
file is saved in `/root/custom-apk-feed-backup-20261014/`.

HTTP serves only APKs, signed indexes, manifests, and repository lists from
this separate publication directory. Directory listings, private keys,
firmware images, and the build tree are not exposed. Requests are limited to
`192.0.2.0/24`; APK signature verification remains enabled on the router.

## Kernel hash mismatch

The running router remains on its original ABI:

```text
kernel package: 6.18.55~ef561c78a2b577ae422f9289311ff293-r1
configuration hash: ef561c78a2b577ae422f9289311ff293
```

The rebuilt desktop-kernel image uses a different ABI:

```text
kernel package: 6.18.55~f10b60a7da5b97b579b974213f7b729c-r1
configuration hash: f10b60a7da5b97b579b974213f7b729c
```

Publish a completed build into its own ABI namespace automatically:

```sh
./scripts/publish-changed-feeds.sh --dry-run
./scripts/publish-changed-feeds.sh
```

Alternatively use `./scripts/build-and-publish.sh -j16 V=s` for both steps.
The publisher checks every direct kernel dependency and the signed kernel
APK version. It creates a separate ABI alias atomically and retains the old
router's publication. There is deliberately no global `latest` alias.

The image selects `CONFIG_PACKAGE_lan-apk-feeds=y`. Its router configuration
is `/etc/lan-apk-feeds.conf`, containing the LAN origin and repository names,
with no kernel hash. The helper `/usr/sbin/lan-apk-feeds-sync` reads the exact
installed kernel version from APK's installed database and atomically writes
all nine URLs. `/etc/init.d/lan-apk-feeds` is enabled for boot; an APK post-commit
hook also refreshes the file. Neither path accesses the network or installs
packages. The helper safely migrates the earlier local custom URL out of
`customfeeds.list`, preserving unrelated URLs and comments. Unmarked,
unrecognized `lan-local.list` contents are rejected rather than overwritten.

After deploying matching new firmware, the boot helper switches its feed URLs
automatically. Until then, the old router continues using its old ABI even
when the build host publishes a new one. Existing exact kernel constraints
in `/etc/apk/world` are untouched. Sysupgrade normally excludes the old world
file; the rebuilt image supplies its matching pin. Keep this helper package
selected in subsequent firmware builds. Missing publications fail normally
at `apk update`; the client never falls back to another ABI.

OpenWrt derives this package dependency hash from sorted kernel configuration
entries set to `y` or `m` (`include/kernel-defaults.mk`). Matching `uname -r`
alone is insufficient. Changing the selected kmods can change the hash.
The APK kernel constraint protects package selection; it does not independently
prove kernel source or symbol compatibility.

For an existing matching module, use this ABI-specific local feed. For a new
module, rebuild against the exact firmware source, patches, kernel
configuration, and toolchain used for the running kernel. Check the resulting
`.vermagic` and package dependencies before publishing. Preserve that build
context before updating or cleaning the checkout.

If the build has a different kernel ABI, publish it under its own kernel
version. The router's existing URL stays on the old ABI. Moving the router to
that new ABI requires matching firmware deployment and reboot. The helper
then selects matching URLs automatically. That deployment was not performed here.
Do not rewrite `.vermagic`, edit package dependencies to claim a false match,
remove the kernel pin, or force incompatible modules into the running system.
See OpenWrt's [kernel dependency guidance](https://openwrt.org/faq/cannot_satisfy_dependencies).

### Desktop-kernel publication on 2026-10-14

The desktop-kernel ABI above was published as snapshot
`20261014T064100.759892Z`. It contains nine signed repositories: `target`,
`base`, `luci`, `packages`, `passwall_luci`, `passwall_packages`, `taskplan`,
`video` and `custom`. The source set has 1,094 APK files; projection into
`custom` produces 1,170 repository entries, including duplicate copies.
There are 251 kernel-dependent entries, all pinned to the new ABI.

The dry run, publication and unchanged incremental rerun passed. All nine
indexes were fetched over HTTP and signature-verified. The existing router
downloaded the new target index and `kmod-vhost-net` APK, verified both with
its existing trust keys, and confirmed the module's exact new-kernel
dependency. No package was installed.

The old ABI alias, all 1,033 previously published APK files and all old index
hashes were verified unchanged. The publisher's eight regression tests also
passed, including wrong-ABI rejection and retained-snapshot immutability.
The service remains running without a restart. Validation evidence is under
`/srv/openwrt-validation/openwrt-feed-publish-validation-20261014-144027/`.

## Service, address, and rollback

The installed unit is `/etc/systemd/system/lan-apk-feeds.service`; its source
template is `configs/lan-apk-feeds.service`. The installed server script is
`/usr/local/lib/openwrt-feeds/serve-lan-apk-feeds.py`.

```sh
sudo systemctl status lan-apk-feeds.service
sudo journalctl -u lan-apk-feeds.service
```

The router has a dedicated DHCP reservation `dhcp.lan_apk_feeds_host` for
`02:00:00:00:00:01` at `192.0.2.164`. If the build host bridge MAC or LAN
changes, update that reservation, the service bind address, the publisher's
`base_url`, and `/etc/lan-apk-feeds.conf` together, then run
`sudo /etc/init.d/lan-apk-feeds restart`. The configuration is a package
conffile and survives sysupgrade; boot regenerates the ABI-specific list.

Router backups are in `/root/lan-apk-feeds-backup-20261014`: previous feed
files, world constraints, DHCP configuration, sysupgrade configuration, and
before/after package, module, kernel, network, firewall, and boot checks.

To remove this setup, first disable/remove `lan-apk-feeds` so it no longer
regenerates the list. While preserving other subsequent changes, remove
`/etc/apk/repositories.d/lan-local.list`, remove its explicit line from
`/etc/sysupgrade.conf`, remove the local custom URL from `customfeeds.list`,
and delete only `dhcp.lan_apk_feeds_host` with UCI,
commit DHCP, and reload dnsmasq. On the host, disable the server with
`sudo systemctl disable --now lan-apk-feeds.service`. Retain backups and
published snapshots until they are no longer needed.

To roll back a publication, atomically point the ABI symlink at a retained
matching snapshot, then run `sudo apk update`. This rolls back feed contents,
not packages already installed from them.

## Validation on 2026-10-14

- Published 957 signed packages in eight repositories, including 130
  kernel-dependent packages, with signatures and direct ABI dependencies checked.
- Physical-router `apk update` passed: 1028 distinct packages available
  (including installed packages not present in the current publication).
- Downloaded `kmod-tun` over LAN and passed `apk verify` using existing router keys.
- `apk add --simulate --force-reinstall kmod-tun` selected only that module.
  All published kmods were already installed on this router, so no additional
  module was installed or loaded for this validation.
- A requested wrong kernel ABI was rejected before changing the active feed.
- Private-key paths and directory listings returned HTTP 403; an unpublished
  ABI URL returned 404.
- Host service restart and a subsequent router `apk update` passed. The unit
  is enabled for boot; the host was not rebooted to test startup.
- Router boot ID, installed package list, kernel image hash, all module-file
  hashes, network configuration, and firewall configuration were unchanged.
  procd and dnsmasq remained active; LuCI HTTPS returned 200.

No router package was installed, no firmware was flashed, and the router was
not rebooted. The dedicated DHCP reservation was the only DHCP configuration change.

## Incremental publisher validation

`python3 scripts/tests/test-lan-apk-publisher.py` exercises real signed APK
fixtures in temporary build/publication directories. Eight cases cover
unchanged runs, version upgrades with retained old outputs, reuse of unaffected
indexes, same-version payload changes without mutating old snapshots,
dry-run isolation, wrong kernel dependencies, protected kernel-package
changes, unsigned APKs, and conflicting custom copies.

The real LAN publication was migrated to hash inventory schema 2 without
changing APK or index bytes. A second production run examined 957 source
APKs and reported `unchanged`; the physical router's `apk update` succeeded.
Validation artifacts are in
`/srv/openwrt-validation/incremental-feed-validation-20261014/`.

## Automatic ABI selection validation on 2026-10-14

The combined build/publish command published snapshot
`20261014T070716.050524Z` with only `base` and `custom` indexes changed (the
new helper package). It has 1,095 source APKs and 1,172 repository entries.
All nine HTTP indexes passed signature verification; the old router's alias,
manifest and all 1,033 old APK hashes stayed unchanged. A subsequent plain
publisher invocation detected the build ABI and reported `unchanged`.

Thirteen signed-APK publisher tests and eight client tests passed. The build
wrapper's success/failure gating also passed in isolation. `make -j16 V=s`
completed; the pre-existing unrelated WeeChat Kconfig cycle warning remains
unchanged, and `.config` changed only by selecting `lan-apk-feeds`.

The exact rebuilt EFI image SHA256 is `a3e7dec7bf301901bf8a9713e15a85621844d94ada81ea8191e21e27d745755c`
(581,056,418 bytes), matching `profiles.json`. Cold boot in OVMF
selected all nine matching repositories. Reinstalling the signed helper
exercised the post-commit hook. Restoring old-ABI repository files and
rebooting the VM regenerated matching URLs and retained an unrelated custom
feed. Existing systemd and desktop-kernel smoke checks, including nested
Hyper-V QEMU/libvirt, passed. The test VM was shut down.

The physical router signature-verified the same APK and simulated a
single-package installation before installing it. It remains on its old
kernel ABI; all nine old-ABI feeds refreshed successfully. Only the helper
was added to the package inventory and world. Kernel, existing kernel pin,
loaded module names, boot ID, network, firewall and DHCP hashes were
preserved. No firmware flash or router reboot occurred. The one-time local
APK checksum pin for the helper was replaced with the normal package name
without any package changes. Backups are in
`/root/lan-apk-feeds-auto-backup-20261014.t3Gk2w/config-before.tar.gz`.

Evidence: `/srv/openwrt-validation/openwrt-feed-auto-validation-20261014/`.
