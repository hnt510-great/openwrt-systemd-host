# GitLab source synchronization validation (2026-11-14)

Integrated GitLab main updates after `b2a948f453ae4ac264307e26469f70279372bc49`
through `8b607ac3994bf875a798ffa444701aa52cb7cc5e` onto the public tree on
branch `sync/gitlab-20261114`. All 64 non-merge commits (44 OpenWrt upstream
commits from `ada52cc7ed..24c13d794c` and `24c13d794c..e2ed57b957`, plus 20
local integration commits) have individual provenance records
(`GitLab-source:` trailers). Original author names, email addresses, dates,
and `Signed-off-by` / `Co-Authored-By` trailers were preserved and verified
against GitLab. Private GitLab history is not a merge parent.

Major changes integrated include `gnome-remote-desktop` dma-buf fd retention
and Vulkan VA-API H.264 RDP acceleration (`freerdp` 3.33.1-r2,
`libmesa-virtualization` Vulkan ICD mirror), Google Chrome stable tracking and
`google-chrome-bin` (157.0.8103.78), `openwrt-desktop` APK icon-theme refresh
hook and bundled GNOME applications (`wl-clipboard`, `resources`,
`gnome-text-editor`, `loupe`, `gnome-calculator`, `baobab`, `file-roller`,
`evince`, `poppler`, `gtksourceview`, `libspelling`), `needrestart` r14 Podman
pod infra/helper and Chrome zygote sandbox support, `sunshine` reproducible
build cleanup, Linux 7.3 backports for upstream 6.18 SFP/phylib changes,
`firewall4` 2026-11-08 update with rebased fullcone/discovery patches,
`hid-multitouch` deduplication, upstream Realtek DSA/PCS updates, and `tpm2-tss`
4.2.2 / `cmake-bin` 4.5.0 / `libudisks2` 2.12.0 / `libostree` 2026.7 updates.

Merge and conflict resolutions against public-only tree differences:

- `firewall4: update to Git HEAD (2026-11-08)` (`dab12e7663`): applied the
  refreshed `package/network/config/firewall4/patches/{001,002,005,006,007,008}-*.patch`
  resolutions from GitLab merge `4668dfbe4b`, retaining the existing
  `Project contributors <contributors@example.invalid>` header in `008`.
- `kernel: add the hid-multitouch module` (`b0f96dc621`): took GitLab merge
  `4668dfbe4b`'s deduplicated `package/kernel/linux/modules/input.mk`.
- `package/custom/luci-theme-argon` (`b5417f52da`): kept the public submodule
  gitlink at `9e263d988b7be4d619442f297f4105871e12808` with an empty
  provenance commit because `148cc76248bfdcd617759ee430a6c613ddd26c83` is not
  present on the public GitHub remote.
- `configs/gnome-desktop.config`, `configs/x86-64-systemd-desktop.config`, and
  `configs/custom-package-updates.json`: preserved public-only
  `luci-app-desktop-setup` (`luci-i18n-desktop-setup-zh-cn`) and
  `libmesa-virtualization` selections alongside the new Chrome/GNOME additions.
- Personal identifiers in newly added documentation sections were redacted
  without altering author attribution or patch `From:` author/email headers:
  private validation paths use `/srv/openwrt-validation/...`, router IP and
  SSH references use `192.0.2.1` / `router-admin@192.0.2.1`, and `needrestart`
  `r14` container/pod/UID examples use `example-infra` (`000000000001`),
  `example-pod.service`, and UID `1000`. Existing `luci-app-desktop-setup`,
  `system-description.systemd.md` (`apk.example.invalid`), `docs/gnome-desktop*.md`,
  and prior `192.0.2.1` / `/srv/openwrt-validation` redactions were retained.

The five updated ignored `feeds/*` repositories were also merged locally
(`--no-ff`, preserving existing `README*.md` and anonymized `mesa` patch
headers) and re-indexed with `./scripts/feeds update -i -a` and
`./scripts/feeds install -a`; `routing` (`2ae1f6df7b`), `taskplan`
(`063b5fe5c9`), and `telephony` (`bb55bb952a`) had zero incoming commits:

- `feeds/packages`: `89847b7338` (merged `gitlab/master` `9c6a80d3c9`)
- `feeds/luci`: `040018904c` (merged `gitlab/master` `e46e6390ee`)
- `feeds/video`: `71e0865eed` (merged `gitlab/master` `412afe7a1b`)
- `feeds/passwall_luci`: `630c863bd9` (merged `gitlab/main` `041ba0d479`)
- `feeds/passwall_packages`: `23b8babb90` (merged `gitlab/main` `c1937c6165`)

| Check | Result |
| --- | --- |
| Author attribution | All 64 replayed commits match original author names, emails, dates, messages, and `GitLab-source:` trailers |
| Personal marker scan | Scanned added lines and commit messages across all 64 main commits and incoming feed commits; zero leaked personal IPs, paths, accounts, or private container IDs (3 new `patches/feeds/0035..0037` keep original `From:` author/email header per policy) |
| Content parity | All 179 modified files match sanitized `gitlab/main`, with diffs confined to the 10 expected redacted/public-merged files (`171` untouched files match pre-existing public deltas from `b2a948f453..main`) |
| Whitespace (`git diff --check`) | Passed on `main..sync/gitlab-20261114` (`0` issues) |
| `scripts/feeds update -i -a` & `install -a` | Exited 0; feed indexes regenerated cleanly |
| `test-custom-package-updates.py` / `test-firefox-updater.py` | 49 passed / 7 passed |
| `test-desktop-icon-theme-hook.py` / `test-desktop-setup.py` / `test-rtkit-desktop.py` | 2 passed / 19 passed / 12 passed |
| `test-needrestart.py` / `test-luci-needrestart.py` | 109 passed / 7 passed |
| `test-gnome-rdp-audio-latency.py` / `test-gnome-rdp-listener.py` / `test-desktop-audio.py` / `test-desktop-ime.py` / `test-gnome-keyring.py` | 1 / 1 / 3 / 1 / 1 passed |
| `test-mainline-kernel-updates.py` / `test-kernel-build-inputs.py` / `test-kernel-bundle.py` / `test-kernel-upgrade.py` | 20 / 7 / 8 / 41 passed (`test-kernel-apk-policy.py`: 25 skipped, no built kernel APKs) |
| `test-build-and-publish.py` / `test-allocate-rebuild-releases.py` / `test-diagnose-apk-rebuild.py` | 68 / 9 / 14 passed |
| `test-apk-upgrade-preflight.py` / `test-elf-abi.py` / `test-ucode-abi.py` / `test-merge-usr.py` / `test-package-metadata-kconfig.py` / `test-lan-apk-publisher.py` | 37 / 23 / 6 / 9 / 4 / 26 passed (`test-apk-source-versions.py` errored on pre-existing `nginx-ssl-util` `1.7-r8` ledger reservation present in `main` prior to sync) |
| `test-uci-history.py` / `test-uci-history-units.py` / `test-luci-uci-history.py` | 39 / 2 / 4 passed |
| `test-boot-readiness.py` / `test-network-wait-online.py` / `test-systemd-service-bridge.py` / `test-openwrt-installer.py` / `test-router-audit.py` / `test-router-audit-connections.py` | 10 / 14 / 25 / 7 passed (2 skipped) / 29 / 8 passed |
| Node.js LuCI view suites (`firewall-fullcone`, `needrestart`, `desktop-setup`, `status-redraw`, `uci-history-view`) | All 5 suites passed |
| `test-alternatives.sh` | Passed |

Scope: local source synchronization across `openwrt-systemd-host` and the
active `feeds/*` repositories plus host unit checks only. No firmware/package
build, VM execution, physical-router modification, APK feed publication, or
remote push was performed.
