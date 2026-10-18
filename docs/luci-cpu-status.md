# LuCI CPU temperature and frequency

The stock LuCI overview ends the System card with the load average. This fork
appends the current CPU package temperature and the current CPU frequency:

```
Load Average      0.16, 0.13, 0.19
CPU Temperature   58.0 °C
CPU Frequency     795 MHz
```

The view is `modules/luci-mod-status/htdocs/luci-static/resources/view/status/include/10_system.js`
in the `luci` feed. Rows are only rendered when a value is available, so
images without sensors keep the original card unchanged.

## Data sources

**Temperature** — the first hwmon device whose driver is one of `coretemp`,
`k10temp`, `zenpower`, `cpu_thermal` or `soc_thermal` is used, reading
`temp1_input` (Intel `Package id 0`, AMD `Tctl`). If no such driver exists the
first `/sys/class/thermal` zone whose `type` matches `pkg|cpu|soc|core` is
used, falling back to the first valid zone. The value is millidegrees Celsius
divided by 1000.

**Frequency** — `/sys/devices/system/cpu/online` is parsed into a CPU list and
`cpufreq/scaling_cur_freq` is read for every CPU; the arithmetic mean is
displayed. Without cpufreq (for example in a VM) the `cpu MHz` lines of
`/proc/cpuinfo` are averaged instead. Values at or above 1 GHz are shown in
GHz, below that in MHz.

Because the overview refreshes every include at once, the burst of RPC calls
briefly drives all cores to their boost clock. The frequency read therefore
waits 800 ms after the include starts, which keeps an idle system near its
idle clock instead of reporting the dashboard's own refresh burst.

## Permissions

Reading sysfs goes through rpcd's `file` object, so
`modules/luci-mod-status/root/usr/share/rpcd/acl.d/luci-mod-status-index.json`
grants `luci-mod-status-index`:

- `list` on `/sys/class/hwmon` and `/sys/class/thermal`
- `read` on `/sys/class/hwmon/hwmon*/name`, `.../temp*_input`,
  `/sys/class/thermal/thermal_zone*/{type,temp}`
- `read` on `/sys/devices/system/cpu/{online,cpu*/cpufreq/scaling_cur_freq}`
- `read` on `/proc/cpuinfo`

rpcd resolves symlinks and re-checks the target against the ACL, so the
resolved paths are granted as well: `/sys/devices/*/hwmon/hwmon*`,
`/sys/devices/*/thermal_zone*` and
`/sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq` (the `cpuN/cpufreq`
directory links to `cpufreq/policyN`).

## Translations

`CPU Temperature` and `CPU Frequency` are translated in
`modules/luci-base/po/zh_Hans/base.po` as `CPU 温度` and `CPU 频率`. Other
languages fall back to English until translated upstream.

## Feed provenance

| Item | Value |
| --- | --- |
| Feed | `luci`, `https://github.com/openwrt/luci.git` |
| Base | `816a314705c9a79a9db2a968fbd80ccdd3ae119e` |
| Local commit | `5405dabc43fd3767d5036b0e15f1c0a4f91c010a` |
| Mirror | `patches/feeds/0001-luci-status-cpu-stats.patch` |
| Manifest | `configs/luci-feeds.json` |

On a clean checkout with the recorded base:

```bash
git -C feeds/luci am "$PWD/patches/feeds/0001-luci-status-cpu-stats.patch"
./scripts/feeds install -a
```

Do not apply the patch when the feed working tree already contains the commit.

## Validation

See [luci-cpu-status-validation.md](luci-cpu-status-validation.md). Evidence is
kept outside the repository in
`/srv/openwrt-validation/luci-cpu-status-validation-20261018/`.
