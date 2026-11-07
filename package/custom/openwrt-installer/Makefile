include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-installer
PKG_VERSION:=1
PKG_RELEASE:=2
PKG_LICENSE:=GPL-2.0-only
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-installer
  SECTION:=base
  CATEGORY:=Base system
  TITLE:=Whole-disk USB installer
  DEPENDS:=@TARGET_x86_64 @OPENWRT_SYSTEMD +python3-light +python3-uuid +python3-openssl +whiptail +sfdisk +e2fsprogs +btrfs-progs +xfs-mkfs +dosfstools +lsblk +blkid +losetup +grub2-bios-setup +openssl-util +partx-utils +wipefs +mount-utils +coreutils-dd +shadow-useradd +shadow-usermod +shadow-groupadd +sudo +kmod-fs-btrfs +kmod-fs-xfs
endef

define Build/Compile
endef

define Package/openwrt-installer/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/usr/lib/openwrt-installer $(1)/usr/libexec/openwrt-installer
	$(INSTALL_BIN) ./files/openwrt-installer $(1)/usr/sbin/
	$(INSTALL_DATA) ./files/{core,apply,tui}.py $(1)/usr/lib/openwrt-installer/
	$(INSTALL_BIN) ./files/firstboot $(1)/usr/libexec/openwrt-installer/
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system $(1)/etc/systemd/system/multi-user.target.wants
	$(INSTALL_DATA) ./files/*.service ./files/*.target $(1)/usr/lib/systemd/system/
	$(LN) /usr/lib/systemd/system/openwrt-installer-firstboot.service $(1)/etc/systemd/system/multi-user.target.wants/
endef

$(eval $(call BuildPackage,openwrt-installer))
