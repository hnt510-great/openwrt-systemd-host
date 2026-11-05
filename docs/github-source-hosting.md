# GitHub source hosting

The main tree is `https://github.com/hnt510-great/openwrt-systemd-host.git`. It uses ten
public repositories: the main tree, eight active feeds, and the Argon theme.
The complete source, branch and original upstream map is
[`configs/github-source-repositories.json`](../configs/github-source-repositories.json).
These are independent public repositories containing the local Git histories.

The main tree, all eight active feeds and the Argon theme can be cloned over
HTTPS without signing in to GitHub. Authentication and write access are needed
only when pushing changes.

```sh
git clone https://github.com/hnt510-great/openwrt-systemd-host.git
cd openwrt-systemd-host
./scripts/feeds update -a
./scripts/feeds install -a
```

The `custom` feed links to `package/custom` in the main tree. The feed updater
initializes its Argon Git submodule from the sibling public theme repository.
It also checks registered custom package versions against their original
upstreams and may edit recipes. To reproduce only saved source recipes, clone
the eight Git feeds by their names, initialize the theme submodule, link the
custom feed and regenerate its index; the validation record lists these steps.

The retired `argon_config` feed is saved on the theme repository's separate
`retired-argon-config` branch. It is not an active feed. Its `local_branch`
manifest field describes the original migration checkout; use `branch` when
cloning the archived feed.

The main tree's authoritative source is the private GitLab instance; GitHub
`origin` is the public publishing destination. The official OpenWrt URL in the
map records code ancestry, not this checkout's synchronization upstream.
Each feed has its own history and original project listed in the map. Maintainers
can add an `upstream` remote in the appropriate feed, merge and test its changes,
then publish reviewed changes with explicit authorization. Other machines obtain
those changes through `scripts/feeds update`; that command does not merge
original feed upstreams automatically. See [local build](local-build.md) for an
example and configuration setup.

Inherited GitHub Actions are disabled on all ten repositories. This source
migration does not enable host scheduled maintenance, publish APK feeds or
deploy a device. Ignored overlays, signing material, stashes and private
backup/automation refs are not included in branch uploads. Existing commit
history and author metadata remain unchanged.

See [validation](github-source-hosting-validation.md).
