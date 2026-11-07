# GitLab feed synchronization validation (2026-11-07)

Checked all eight active feeds against their private GitLab mirrors. Exact source
and local integration commits are recorded in
`configs/gitlab-feed-sync-20261107.json`. Feed histories remain independent of
the main source repository; historical `patches/feeds/` backups were not reapplied.

| Feed | Incoming commits | Local result |
| --- | ---: | --- |
| packages | 52 | Merged as `2337e60dad` |
| luci | 9 | Merged as `680d278057` |
| video | 8 | Merged as `d255a21dc9` |
| passwall_luci | 10 | Merged as `aa01308d2f` |
| passwall_packages | 0 | Already contains GitLab tip |
| telephony | 0 | Already contains GitLab tip |
| routing | 0 | Already contains GitLab tip |
| taskplan | 0 | Already contains GitLab tip |

The routing and taskplan GitLab URLs were supplied by the user and added as
`gitlab` remotes. Existing GitHub publication remotes and feed defaults remain.
All four merges were conflict-free. They preserve public README additions,
local integration commits and GitLab's existing merge resolutions, including
OpenSSH 10.6p2, fuse3 3.18.3, Mesa release 10 and independent Passwall code and
translation revisions. Original source commits, author names, emails and
co-author attribution are preserved unchanged.

Incoming history was reviewed for personal home paths, account/key identifiers,
private operational LAN details and credential markers. None required redaction.
The LuCI translation's DNS option example uses a conventional private subnet;
it is generic upstream documentation, not evidence about a personal network.
Contributor attribution and translator headers are retained.

| Check | Result |
| --- | --- |
| GitLab source ancestry | All eight source tips contained in resulting local branches; all feed worktrees clean |
| Gitleaks 8.30.1 | All four incoming history ranges scanned; zero findings |
| Lua syntax | 1 changed script passed with existing host Lua 5.1 |
| Shell syntax | 9 changed scripts passed |
| JavaScript syntax | 4 changed views passed compilation as LuCI function bodies |
| ucode syntax | 7 changed modules/scripts passed; rpcd backend passed with its body wrapped as a function; external imports left dynamic for host compilation |
| Translation format | 371 changed PO files passed `msgfmt --check-format` |
| Patch application | 2 libcups patches and 6 Mesa patches applied to cached original source archives |
| Passwall independent versions | 1 focused regression test passed |
| Custom recipe registry | 47 tests passed |
| Full source-version regression | Same two existing reserved-future-release errors for nginx-ssl-util and native-libs-dev documented in the earlier source synchronization; affected recipes are unchanged by this feed merge |
| Feed metadata | Four indexes regenerated without fetching other upstreams; generated package links refreshed and links to deleted recipes removed |
| Whitespace | Source-file checks passed in all four feeds; imported patch files retain upstream diff-context whitespace warnings |

The first direct ucode compilation attempt lacked module mode/import paths;
checks were rerun with module mode and dynamic imports. The rpcd callback body
was syntax-checked in a function wrapper. These are syntax checks, not target
runtime tests. Patch application used disposable extracted source directories.

Scope: local GitLab source merges, metadata refresh and host checks. No full
package/firmware build, VM/device validation, APK publication, deployment or
GitHub push was performed. Existing README edits, working configuration,
personal overlays, theme checkout and unrelated feed histories were preserved.
