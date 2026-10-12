include $(TOPDIR)/rules.mk

PKG_VERSION:=1.0.0
PKG_RELEASE:=1
PKG_LICENSE:=Apache-2.0

LUCI_TITLE:=LuCI QEMU virtual machine management
LUCI_DEPENDS:=+luci-base +rpcd-mod-ucode +ucode-mod-fs +virsh +libvirt-daemon +coreutils-timeout
LUCI_PKGARCH:=all
LUCI_EXTRA_DEPENDS:=libvirt-daemon (>=12.8.0-r2)

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
