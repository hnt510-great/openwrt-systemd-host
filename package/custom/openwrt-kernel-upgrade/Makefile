include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-kernel-upgrade
PKG_VERSION:=1
PKG_RELEASE:=19
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-kernel-upgrade
  SECTION:=base
  CATEGORY:=Base system
  TITLE:=Parallel ABI-pinned kernels and protected GRUB recovery
  DEPENDS:=@OPENWRT_SYSTEMD +python3 +openwrt-kernel-policy +grub2-editenv +grub2 +grub2-efi +kmod +ubox +blkid +ldd
  EXTRA_DEPENDS:=openwrt-kernel-policy (>=3.0.5-r18), ubox (>=2025.10.30~6f78fa49-r3), systemd-openwrt (>=6), grub2 (>=2.12-r4), grub2-efi (>=2.12-r4)
endef

define Package/openwrt-kernel-upgrade/conffiles
/etc/openwrt-kernel/
endef

define Build/Compile
endef

define Package/openwrt-kernel-upgrade/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/usr/libexec $(1)/etc/openwrt-kernel
	$(INSTALL_BIN) ./files/kernelctl $(1)/usr/sbin/kernelctl
	$(INSTALL_BIN) ./files/init $(1)/usr/libexec/openwrt-kernel-init
	$(INSTALL_DIR) $(1)/etc/init.d
	$(INSTALL_BIN) ./files/kernel-generation.init $(1)/etc/init.d/kernel-generation
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system $(1)/etc/systemd/system/multi-user.target.wants
	$(INSTALL_DATA) ./files/openwrt-kernel-boot.service $(1)/usr/lib/systemd/system/
	$(INSTALL_DATA) ./files/openwrt-kernel-prune.path $(1)/usr/lib/systemd/system/
	$(INSTALL_DATA) ./files/openwrt-kernel-prune.service $(1)/usr/lib/systemd/system/
	$(LN) /usr/lib/systemd/system/openwrt-kernel-boot.service $(1)/etc/systemd/system/multi-user.target.wants/
	$(LN) /usr/lib/systemd/system/openwrt-kernel-prune.path $(1)/etc/systemd/system/multi-user.target.wants/
endef

$(eval $(call BuildPackage,openwrt-kernel-upgrade))
