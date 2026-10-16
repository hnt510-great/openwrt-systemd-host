# Scheduled build Kconfig repair

Validated in place on 2026-10-16 for the x86_64/glibc native-systemd tree.
The scheduler failure log and repository provenance are in
`/srv/openwrt-automation/runs/20261016T040823Z/`.

## Root causes and changes

- Weston: `PACKAGE_weston` inherits target/libc constraints from its
  conditional Xwayland dependency. `WESTON_XWAYLAND depends on PACKAGE_weston`
  closes the dependency cycle. Express the existing Xwayland x86_64/glibc
  prerequisites directly on the option, without the package dependency.
  The option remains disabled by default and only affects Weston when built.
  VNC, RDP, Xwayland build flags and conditional library dependencies remain.
- WeeChat: LuCI's virtual `weechat` dependency selects the minimal provider
  when the full provider is insufficient. The explicit conflict on the full
  provider introduces a reverse dependency through the selected minimal
  provider. Put the conflict on the default minimal provider instead,
  matching the direction of implicit default-provider conflicts in the
  metadata generator. Both variants, full-provider preference, scripting
  options and the exclusion of simultaneous built-in variants remain.
  Increment WeeChat's release to r2 for its changed conflict metadata.

The independent feed commits and exact patch bases are recorded in
`configs/scheduled-kconfig-feeds.json`. The two exported patches contain only
these source fixes. Their reverse-application checks pass against the fixed
feeds; apply them only where the corresponding repair is absent.

## Validation

The standard metadata scan and feed indexes were regenerated with:

```sh
make prepare-tmpinfo -j1 V=s
./scripts/feeds update -i packages video
```

The scheduler's exact command exits 0 and reports `No change to .config`:

```sh
scripts/config/conf --fatalrecursive --defconfig=.config -w .config Config.in
```

All 38 full-tree strict configuration fixtures pass without stderr:

- Current configuration: normalized output is byte-for-byte identical.
- Eight combinations of Weston VNC/RDP/Xwayland flags, retaining their
  conditional package dependencies. Desktop/AppImage/Flatpak/virt-manager
  selectors are disabled only in temporary fixtures so the flags can vary.
- Twenty-seven n/m/y combinations of LuCI and the two WeeChat providers:
  LuCI stays selected, full-provider selection is retained, the virtual
  dependency is satisfied and both providers are never built in together.
- Each WeeChat variant with all scripting/compression/JSON options enabled.

These package compiles also pass:

```sh
make package/feeds/video/weston/compile -j4 V=s
make package/feeds/packages/weechat/compile -j4 V=s
make -C feeds/packages/net/weechat TOPDIR=/srv/openwrt-validation/openwrt BUILD_VARIANT=full compile -j4 V=s
```

Weston's Meson build options confirm `backend-vnc`, `backend-rdp`, and
`xwayland` are all true. WeeChat's minimal and full variants compile; the
unselected variants were not installed on a running system. An initial
attempt to force `BUILD_VARIANT=full` from the top-level package target was
interrupted because it propagated the variant to dependencies; the scoped
package-directory command above completed instead.

Existing metadata warnings about missing BMX7 packages and the
intel-gpu-tools build-dependency names remain outside this dependency-cycle
repair. They did not prevent strict configuration validation or the affected
package compiles.

## Preservation and limits

The working `.config` SHA256 remains
`8baeb0eb8911e4d04938948f7069e80be0708e6782a92934383bc7ff63bf6d62`.
No selected feature, kernel source/configuration, kernel ABI policy, strict
validator, scheduler, or feed publisher was changed. Existing upstream
integration remains in ancestry. Commits use alternate indexes and advance
only the repair's entries in the normal indexes; unrelated staged/unstaged
work, untracked files, overlays and original stashes are preserved.

Evidence, fixtures, compile logs and preservation checks are under
`/srv/openwrt-automation/runs/20261016T040823Z/repair-kconfig/`.
No full firmware image build or runtime acceptance is claimed; the scheduler
will retry the full build. No publication, push, or physical-router operation
was performed.
