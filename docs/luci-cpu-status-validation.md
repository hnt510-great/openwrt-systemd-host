# LuCI CPU temperature and frequency validation

Validated on 2026-10-18 against the physical router at `192.0.2.1`
(x86_64, glibc, native systemd, kernel
`6.18.55-owrt-1e6d3a41204c57acfef0c7a584b7cc0e-r1-g16`). No firmware image
was rebuilt, flashed or rebooted; validation covers the published APK upgrade
and the authenticated LuCI page.

## Artifacts

| Package | SHA256 |
| --- | --- |
| `luci-mod-status-26.291.12612~5405dab.apk` | `fb4b9ae0520aca46755409dc650f102c0d23d4e6e19f66ccb1c8d46b530e4032` |
| `luci-i18n-base-zh-cn-26.291.12612~5405dab.apk` | `ea9b143434ceddaa632f573c7813f7a5ab1f35b07dd90baca8caeb9aaa1fbc1a` |

Built from luci feed commit `5405dabc43fd3767d5036b0e15f1c0a4f91c010a`,
mirrored as `patches/feeds/0001-luci-status-cpu-stats.patch`.

## Checks

| Check | Result |
| --- | --- |
| LuCI feed commit and patch mirror | `5405dabc`; manifest recorded in `configs/luci-feeds.json` |
| Incremental publication dry-run | Only `luci-mod-status` and `luci-i18n-base-zh-cn` in repo `luci`; kernel unchanged |
| Publication to `http://192.0.2.164:8088` | Both APKs served with HTTP 200 |
| Upgrade through the router's LAN feed | `apk upgrade luci-mod-status luci-i18n-base-zh-cn` moved both to `26.291.12612~5405dab` |
| Installed JS payload | `e99c0ef2de97594716e0f882dc897acb0a946fba37e44b3bb344b89ed0b97640`, identical to the build output |
| Installed ACL payload | `a79a21015cfda23f2d3ee49887b86584c6d97404ae2de17b5032336120fe36d5` |
| Installed zh-cn catalog | `6866a2e237c8d90ae0dcab6f3f9f7f2a232b177cc941fdae6497ee4f06ac18d1` |
| Sensor discovery | `coretemp` hwmon (`temp1_input` 53.0 °C at check time); NVMe and `acpitz` correctly ignored |
| CPU frequency source | four online CPUs, `scaling_cur_freq` around 800 MHz at check time |
| Authenticated Chinese render | `平均负载 0.16, 0.13, 0.19`; `CPU 温度 58.0 °C`; `CPU 频率 795 MHz` |
| Poll refresh | Values and local time update on the configured 5 s `pollinterval` |

The authenticated page was rendered with headless Chrome using a temporary
rpcd session, which was destroyed afterwards. A screenshot and the rendered
page text are in the evidence directory.

## Issues found and fixed during validation

1. The first revision read `data[4]`/`data[5]`, but `uci.load('system')`
   already occupies index 4; the page showed `0.0 °C` / `0 MHz`. Corrected to
   indices 5 and 6.
2. `/sys/devices/system/cpu/cpuN/cpufreq` is a symlink to
   `cpufreq/policyN`, and rpcd re-checks the resolved path. The policy path was
   added to the ACL; without it the frequency silently fell back to
   `/proc/cpuinfo`.
3. Sampling the frequency immediately reported 2.5–2.9 GHz on an idle router
   because the overview's own RPC burst boosts every core. The read now waits
   800 ms, after which the same page reported 789–839 MHz.

## Scope

- Only the two APKs were changed on the router; the kernel, boot ID and
  network configuration were untouched.
- `rpcd` was restarted during an interim manual install while diagnosing the
  ACL path; it was healthy for the final feed upgrade. Existing LuCI sessions
  may have required a re-login after that restart.
- No physical browser session with the user's own credentials was used; the
  page was rendered through a temporary local rpcd session.
- No image was built or flashed, so no statement is made about uninstalled
  images.

## Evidence

`/srv/openwrt-validation/luci-cpu-status-validation-20261018/`

- `overview-zh-cn.png` — authenticated overview with the two new rows
- `rendered-values.json` — captured load, temperature and frequency
- `rendered-page-text.txt` — full rendered page text
- `checks.txt` — installed versions, payload hashes and sensor sources
- `apk-sha256.txt` — published APK checksums
