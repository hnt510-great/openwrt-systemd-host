# Publishing the source repository

The public source tree contains no preset personal account. Create users and
passwords on the device using [multiuser setup](multiuser.md). Keep personal
rootfs overlays, signing keys, SSH material, network credentials and backups
outside this tree. The root `files/` directory remains ignored except for the
11 generic integration files already tracked.

The checked-in LAN publication settings are examples. They use
`apk.example.invalid`, documentation-only `192.0.2.0/24` addresses and an empty
`upgrade_preflight.ssh_target`. Configure the server, service account, listener,
allowed networks, client origin and router SSH target for your installation.
The service example uses the dedicated `openwrt-feeds` account. Production
publication still requires a reachable router and its upgrade preflight.
The changed client defaults are released as `lan-apk-feeds` release 7.

Documentation uses anonymized usernames, paths, domains, network addresses,
MAC addresses and device/boot UUIDs. Evidence paths are illustrative locations,
not downloadable artifacts. Historical validation results describe earlier
runs; anonymization does not claim that the changed source has been built or
validated on hardware.

## Theme repository prerequisite

`.gitmodules` points to `../openwrt-luci-theme-argon.git`, a sibling repository
under the same hosting account or organization as the main project. The public
GitHub hosting layout uses `hnt510-great/openwrt-luci-theme-argon`, including
recorded commit `9e263d988b7be4d6319442f297f4105871e12808`. The main tree, feeds and theme
can be cloned over HTTPS without GitHub authentication. See
[local build](local-build.md) and the
[repository map](../configs/github-source-repositories.json).

## Publication scope

Publish selected source commits through Git. Do not upload a raw workspace or
its `.git` directory as an archive. Ignored `feeds/` repositories and local Git
configuration are not part of the main repository's tracked source. Review
separately any feed repositories you decide to publish. The main tree includes
feed patch files; their personal author headers have been anonymized without
changing patch bodies.

Git history and commit author metadata were deliberately left unchanged.
Removing personal references from the current tree does not remove them from
older commits. This audit does not certify historical credential safety.
The cleanup itself created no GitHub repository and pushed nothing. The later
GitHub migration and subsequent public visibility are separate from that audit; their settings and checks
are recorded in [GitHub hosting validation](github-source-hosting-validation.md).

See [validation](public-source-publication-validation.md) for audit coverage,
scanner findings and test limitations.
