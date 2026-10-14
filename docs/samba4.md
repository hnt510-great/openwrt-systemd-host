# Samba file sharing

The x86_64 native-systemd desktop profile includes Samba 4, its client and
diagnostic utilities, LuCI Network Shares, and the Simplified Chinese
translation. `configs/samba4.config` contains the reusable selections.
NetBIOS, WSD discovery, Avahi discovery, and common VFS modules are enabled.
Active Directory domain-controller support is disabled.

Windows discovers the server through `wsdd2`; Linux and macOS discover its
`_smb._tcp` service through Avahi. The `avahi-utils` package provides tools to
find advertised SMB servers on the local network:

```sh
avahi-browse --resolve --terminate _smb._tcp
```

This lists server names, addresses, and SMB ports. To list a discovered
server's shared folders, use `smbclient -L <server-address> -U <username>`.
The router advertises itself as `OpenWrt` even before any shared folders are
configured. Share paths and access settings remain managed in LuCI.

Configure shared directories under **LuCI → Services → Network Shares**
(`/cgi-bin/luci/admin/services/samba4`). No directory is exported by default.
Choose the path, allowed users, guest access, and read/write permissions there.
For password-protected access, add a Samba password for an existing Unix user:

```sh
sudo smbpasswd -a desktop-user
```

The Samba password is separate from the SSH/Unix password. Clients connect
using `\\192.0.2.1\<share-name>` after a share is configured.

Samba remains managed by OpenWrt UCI and procd through `/etc/init.d/samba4`,
including on the native-systemd image. Useful checks are:

```sh
sudo /etc/init.d/samba4 status
sudo testparm -s
sudo smbclient -L 192.0.2.1 -U desktop-user
```

To build the packages without a VM test:

```sh
make defconfig
make -j4 package/feeds/packages/samba4/compile \
  package/feeds/packages/avahi/compile \
  package/feeds/packages/wsdd2/compile \
  package/feeds/luci/luci-app-samba4/compile V=s
make -j4 V=s
```

For a physical installation, use the matching signed userspace APKs and any
missing userspace dependencies. Simulate the offline APK transaction before
installing it. No kernel package, firmware flash, or reboot is needed.
