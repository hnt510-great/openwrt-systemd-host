include $(TOPDIR)/rules.mk

PKG_NAME:=systemd-openwrt
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/systemd-openwrt
  SECTION:=base
  CATEGORY:=Base system
  TITLE:=OpenWrt native systemd boot and procd compatibility
  DEPENDS:=@OPENWRT_SYSTEMD +systemd +procd +ubusd +ubus +coreutils-timeout +kmod-fs-vfat
endef

define Package/systemd-openwrt/conffiles
/etc/systemd/journald.conf.d/openwrt.conf
/etc/systemd/system.conf.d/openwrt.conf
endef

define Build/Compile
endef

define Package/systemd-openwrt/install
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system $(1)/usr/libexec
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/etc/systemd/system/multi-user.target.wants
	$(INSTALL_DIR) $(1)/etc/systemd/{journald,system}.conf.d
	# x86 preinit must read the EFI partition before restoring upgrade backups.
	$(INSTALL_DIR) $(1)/etc/modules.d $(1)/etc/modules-boot.d
	printf 'nls_cp437\nnls_iso8859-1\n' > $(1)/etc/modules.d/25-systemd-boot-vfat-nls
	$(LN) ../modules.d/25-systemd-boot-vfat-nls $(1)/etc/modules-boot.d/
	$(INSTALL_BIN) ./files/openwrt-rcS $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/openwrt-dbus-ready $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/openwrt-systemd-prepare $(1)/usr/libexec/
	$(INSTALL_DATA) ./files/*.service $(1)/usr/lib/systemd/system/
	$(INSTALL_DATA) ./files/journald.conf $(1)/etc/systemd/journald.conf.d/openwrt.conf
	$(INSTALL_DATA) ./files/system.conf $(1)/etc/systemd/system.conf.d/openwrt.conf
	$(LN) /usr/lib/systemd/system/multi-user.target $(1)/etc/systemd/system/default.target
	for unit in openwrt-ubusd openwrt-procd openwrt-services dbus; do \
		$(LN) /usr/lib/systemd/system/$$$$unit.service $(1)/etc/systemd/system/multi-user.target.wants/; \
	done
	for tty in tty1 $(call qstrip,$(CONFIG_TARGET_SERIAL)); do \
		$(LN) /usr/lib/systemd/system/openwrt-console@.service \
			$(1)/etc/systemd/system/multi-user.target.wants/openwrt-console@$$$$tty.service; \
	done
	for unit in systemd-udevd.service systemd-udevd-control.socket systemd-udevd-kernel.socket \
		systemd-udevd-varlink.socket systemd-udev-load-credentials.service \
		systemd-udev-trigger.service systemd-udev-settle.service systemd-journald-dev-log.socket \
		systemd-sysctl.service systemd-modules-load.service; do \
		$(LN) /dev/null $(1)/etc/systemd/system/$$$$unit; \
	done
	for command in reboot halt poweroff; do \
		sed "s/%COMMAND%/$$$$command/g" ./files/power-command > $(1)/usr/sbin/$$$$command; \
		chmod 0755 $(1)/usr/sbin/$$$$command; \
	done
endef

$(eval $(call BuildPackage,systemd-openwrt))
