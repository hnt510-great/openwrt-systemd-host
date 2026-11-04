# Private GitHub source hosting validation

Date: 2026-11-04. Scope: source hosting, authentication and fresh-checkout feed
reconstruction. No firmware build, VM test, physical-device test, APK feed
publication or device deployment was performed.

| Check | Result |
| --- | --- |
| GitHub identity | Authenticated as `hnt510-great` using the host's GitHub CLI credential store. No credential was added to source URLs or tracked files. |
| Repository privacy | API verification confirmed ten private, independent repositories, with the intended default branches. |
| GitHub Actions | Disabled on all ten repositories before source upload. |
| Main branch and eight active feeds | Uploaded existing local branch histories; remote branch SHA values matched local branches. |
| Shallow feed histories | Fetched missing routing and taskplan history before upload; local branch tips were preserved. |
| Upload size check | No blob of 100 MiB or larger found in the uploaded branch histories. |
| Theme | Uploaded existing `master`, including recorded submodule commit `9e263d988b7be4d6319442f297f4105871e12808`. Original detached working checkout was preserved. Fresh submodule initialization fetched exactly that recorded commit. |
| Retired feed | GitHub creation throttled the eleventh repository. Preserved the complete `argon_config` branch history on the private theme repository's independent `retired-argon-config` branch; SHA matched local `master` (`9f096c916c16be8075610dd137d3b18982f81f1e`). |
| Existing workspace | Retained former remotes, added original `upstream` remotes, and updated active feed location caches to avoid destructive feed relocation. No feed reset or stash operation. |
| Fresh main checkout | HTTPS shallow clone of GitHub `main` succeeded in an isolated temporary directory. |
| Fresh active feeds | `scripts/feeds update` with all eight Git feed names cloned and indexed every private source; each HEAD matched the original workspace. |
| Incremental feed update | Repeated named-feed update after installation succeeded for all eight feeds using the normal pull path; all reported already up to date. |
| Custom feed and installation | Linked `feeds/custom` to `../package/custom`, ran `scripts/feeds update -i custom`, then `scripts/feeds install -a`; all exited successfully and tracked source stayed clean. |
| Custom updater regression tests | 47 tests passed, including feed integration and nested checkout behavior. |
| Scheduled maintenance regression tests | 17 tests passed. No schedule installed or enabled. |
| Syntax and whitespace | `perl -c scripts/feeds` and `git diff --check` passed. |

The fresh-checkout test used the eight explicit feed names to exercise Git
cloning and pulling without changing registered custom package versions.
It tested `git submodule update --init` separately, followed by the custom link,
custom index and package installation. The full network-dependent custom
package update performed by `scripts/feeds update -a` was not run against every
upstream; its existing implementation was covered by the focused regression
tests. This is source reconstruction validation, not build readiness evidence.

Initial package scans emitted missing-dependency warnings while feed links
were not yet installed. Installation also warned that existing core/custom
recipes were not overridden. Commands completed successfully; these checks do
not establish that every selectable package can build.

Evidence: `/tmp/openwrt-github-validation.Qc0mGt/` contains upload output,
`repositories.json`, the fresh-checkout `verify.py`/`verify.log`, and `pull.log`.
Temporary evidence is not committed or guaranteed to persist. Transient TLS/EOF
failures during upload/API calls recovered on retry; no force push was used.
