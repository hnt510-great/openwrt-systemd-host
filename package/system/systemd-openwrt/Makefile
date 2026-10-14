include $(TOPDIR)/rules.mk

PKG_NAME:=systemd-openwrt
PKG_RELEASE:=4
PKG_LICENSE:=GPL-2.0-only
PKG_CONFIG_DEPENDS:=CONFIG_TARGET_ROOTFS_PERSIST_VAR

include $(INCLUDE_DIR)/package.mk

SYSTEMD_LINGER_PATH:=$(if $(CONFIG_TARGET_ROOTFS_PERSIST_VAR),/var,/tmp)/lib/systemd/linger
SYSTEMD_LINGER_UNIT:=$(if $(CONFIG_TARGET_ROOTFS_PERSIST_VAR),var,tmp)-lib-systemd-linger.mount
SYSTEMD_JOURNAL_PATH:=$(if $(CONFIG_TARGET_ROOTFS_PERSIST_VAR),/var,/tmp)/log/journal
SYSTEMD_JOURNAL_UNIT:=$(if $(CONFIG_TARGET_ROOTFS_PERSIST_VAR),var,tmp)-log-journal.mount

define Package/systemd-openwrt
  SECTION:=base
  CATEGORY:=Base system
  TITLE:=OpenWrt native systemd boot and procd compatibility
  DEPENDS:=@OPENWRT_SYSTEMD +systemd +polkit +dbus +procd +ubusd +ubus +coreutils-timeout +kmod-fs-vfat
  DEPENDS+=+openssh-server-pam
endef

define Package/systemd-openwrt/conffiles
/etc/systemd/journald.conf.d/openwrt.conf
/etc/systemd/system.conf.d/openwrt.conf
/etc/systemd/logind.conf.d/openwrt.conf
/etc/pam.d/login
/etc/systemd/linger/
endef

define Build/Compile
endef

define Package/systemd-openwrt/install
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system $(1)/usr/libexec
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/etc/systemd/system/multi-user.target.wants
	$(INSTALL_DIR) $(1)/etc/systemd/{journald,system,logind}.conf.d $(1)/etc/systemd/linger
	# x86 preinit must read the EFI partition before restoring upgrade backups.
	$(INSTALL_DIR) $(1)/etc/modules.d $(1)/etc/modules-boot.d
	printf 'nls_cp437\nnls_iso8859-1\n' > $(1)/etc/modules.d/25-systemd-boot-vfat-nls
	$(LN) ../modules.d/25-systemd-boot-vfat-nls $(1)/etc/modules-boot.d/
	$(INSTALL_BIN) ./files/openwrt-rcS $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/openwrt-dbus-ready $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/openwrt-systemd-prepare $(1)/usr/libexec/
	$(INSTALL_DIR) $(1)/usr/lib/apk/commit_hooks.d
	$(INSTALL_BIN) ./files/kmod-depmod.hook $(1)/usr/lib/apk/commit_hooks.d/20-kmod-depmod
	$(INSTALL_DATA) ./files/openwrt-*.service ./files/dbus.service $(1)/usr/lib/systemd/system/
	$(INSTALL_DATA) ./files/dbus.socket $(1)/usr/lib/systemd/system/
	$(INSTALL_DATA) ./files/journald.conf $(1)/etc/systemd/journald.conf.d/openwrt.conf
	# /var usually aliases /tmp; keep the journal on the persistent root/extroot.
	$(INSTALL_DIR) $(1)/srv/journal $(1)/usr/lib/systemd/system/systemd-journal-flush.service.d
	chmod 2755 $(1)/srv/journal
	$(INSTALL_DATA) ./files/journal.mount $(1)/usr/lib/systemd/system/$(SYSTEMD_JOURNAL_UNIT)
	$(SED) 's,^Where=.*,Where=$(SYSTEMD_JOURNAL_PATH),' $(1)/usr/lib/systemd/system/$(SYSTEMD_JOURNAL_UNIT)
	$(INSTALL_DATA) ./files/journal-flush.conf $(1)/usr/lib/systemd/system/systemd-journal-flush.service.d/openwrt.conf
	$(SED) 's,var-log-journal.mount,$(SYSTEMD_JOURNAL_UNIT),g' \
		$(1)/usr/lib/systemd/system/systemd-journal-flush.service.d/openwrt.conf
	$(INSTALL_DATA) ./files/openwrt-journal-rotate.timer $(1)/usr/lib/systemd/system/
	$(INSTALL_DIR) $(1)/etc/systemd/system/timers.target.wants
	$(LN) /usr/lib/systemd/system/openwrt-journal-rotate.timer $(1)/etc/systemd/system/timers.target.wants/
	$(INSTALL_DATA) ./files/system.conf $(1)/etc/systemd/system.conf.d/openwrt.conf
	$(INSTALL_DATA) ./files/logind.conf $(1)/etc/systemd/logind.conf.d/openwrt.conf
	$(INSTALL_DIR) $(1)/etc/pam.d
	$(INSTALL_DATA) ./files/login.pam $(1)/etc/pam.d/login
	$(INSTALL_BIN) ./files/systemd-access $(1)/usr/sbin/
	$(INSTALL_DIR) $(1)/usr/lib/systemd/user/default.target.wants
	$(INSTALL_DATA) ./files/user-dbus.service $(1)/usr/lib/systemd/user/dbus.service
	$(INSTALL_DATA) ./files/user-dbus.socket $(1)/usr/lib/systemd/user/dbus.socket
	$(LN) ../dbus.service $(1)/usr/lib/systemd/user/default.target.wants/dbus.service
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system/systemd-logind.service.d
	$(INSTALL_DATA) ./files/logind-service.conf $(1)/usr/lib/systemd/system/systemd-logind.service.d/openwrt.conf
	$(INSTALL_DATA) ./files/linger.mount $(1)/usr/lib/systemd/system/$(SYSTEMD_LINGER_UNIT)
	$(SED) 's,^Where=.*,Where=$(SYSTEMD_LINGER_PATH),' $(1)/usr/lib/systemd/system/$(SYSTEMD_LINGER_UNIT)
	$(SED) 's,var-lib-systemd-linger.mount,$(SYSTEMD_LINGER_UNIT),g' \
		$(1)/usr/lib/systemd/system/systemd-logind.service.d/openwrt.conf
	$(LN) /usr/lib/systemd/system/multi-user.target $(1)/etc/systemd/system/default.target
	for unit in openwrt-ubusd openwrt-procd openwrt-services dbus systemd-logind systemd-user-sessions polkit; do \
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
