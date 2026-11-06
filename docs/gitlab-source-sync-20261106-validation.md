# GitLab source synchronization validation (2026-11-06)

Integrated seven GitLab main commits after snapshot
`672b596a340edc36c87abb9bd3a0c092275fff6d` through
`b7cb955d13446ec68d30d789066140b1500e1239`. Each source delta was replayed
onto the previous public integration, preserving its original author name,
author email and author date. Each replay records its source commit hash.
Raw private GitLab history is not a merge parent; existing history is unchanged.

The changes add UCI configuration history and timed rollback, its LuCI page
and rpcd events, plus router audit collection, DNS instrumentation, deterministic
analysis, local-model integration and read-only MCP tools. Public feed defaults,
GitHub source URLs, desktop enrollment and the existing theme gitlink remain.
Personal evidence/home paths, the SSH key filename and the observed account
actor were replaced with public examples. LAN examples and matching synthetic
fixtures use documentation addresses. Author attribution was not redacted.

Host testing exposed SQLite builds that do not interpret URI filenames by
default: the analyzer could not attach its read-only source database. Both cache
connections now explicitly enable URI handling. `router-audit` is release 4
because its packaged source changed. No other upstream behavior was changed.

| Check | Result |
| --- | --- |
| UCI history lifecycle | 38 tests passed |
| LuCI backend | 4 tests passed with the existing host ucode runtime |
| LuCI view | Node assertions passed |
| Unit ordering | 2 tests passed |
| VM console harness | 2 host tests passed; no VM started |
| Router audit | 29 tests passed, including synthetic analysis, cache, fake model endpoint and MCP stdio |
| Custom package registry | 47 tests passed |
| rpcd patch checkpatch | 0 errors, 0 warnings |
| Author attribution | All seven replayed author names and emails match GitLab |
| Personal marker scan | Every new commit delta checked; identified personal paths, account actor, key filename and LAN subnet absent |
| Gitleaks 8.30.1 | Archive checksum verified; 27 findings in unchanged files, zero incoming-file findings |
| Whitespace | `git diff --check` passed |

The isolated worktree initially lacked the host ucode binary, host APK and
populated theme checkout. Tests passed using the existing host staging tools
and a reference to the existing theme recipe; the theme gitlink was not changed.
The initial audit test failure was reproduced with a minimal SQLite attach and
resolved by enabling URI handling explicitly. The timeout fixture can emit an
expected local HTTP BrokenPipe traceback while the assertions still pass.

Scope: local source integration and host checks only. No package or full firmware
build, new VM run, physical-device validation, feed publication, deployment or
GitHub push was performed. Incoming build, VM, model and physical-router records
are historical upstream evidence, not checks rerun during this synchronization.
The working configuration, independent feed repositories, overlays, theme and
preexisting staged deletions/local guidance files are preserved. Scanner reports
and temporary tooling remain outside the repository.
