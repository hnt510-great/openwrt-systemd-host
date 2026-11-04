# Private GitHub source hosting

The main tree is `https://github.com/hnt510-great/openwrt.git`. It uses ten
private repositories: the main tree, eight active feeds, and the Argon theme.
The complete source, branch and original upstream map is
[`configs/github-source-repositories.json`](../configs/github-source-repositories.json).
These are independent private repositories containing the local Git histories.

Authenticate on each build machine before cloning. The account must have read
access to every private repository listed in the map.

```sh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
git clone https://github.com/hnt510-great/openwrt.git
cd openwrt
./scripts/feeds update -a
./scripts/feeds install -a
```

The `custom` feed links to `package/custom` in the main tree. The feed updater
initializes its Argon Git submodule from the sibling private theme repository.
It also checks registered custom package versions against their original
upstreams and may edit recipes. To reproduce only saved source recipes, clone
the eight Git feeds by their names, initialize the theme submodule, link the
custom feed and regenerate its index; the validation record lists these steps.

The retired `argon_config` feed is saved on the theme repository's separate
`retired-argon-config` branch. It is not an active feed. Its `local_branch`
manifest field describes the original migration checkout; use `branch` when
cloning the archived feed.

`origin` points to private GitHub in the migrated workspace, while `upstream`
points to the original project. Earlier remote URLs remain under separate
names. New clones receive only `origin`; maintainers can add `upstream` from
the map. Merge and test upstream changes in the appropriate repository, then
push them to its private branch. Other machines obtain those reviewed changes
through `scripts/feeds update`; that command does not merge original feed
upstreams automatically. See [local build](local-build.md) for an example and
configuration setup.

Inherited GitHub Actions are disabled on all ten repositories. This source
migration does not enable host scheduled maintenance, publish APK feeds or
deploy a device. Ignored overlays, signing material, stashes and private
backup/automation refs are not included in branch uploads. Existing commit
history and author metadata remain unchanged.

See [validation](github-source-hosting-validation.md).
