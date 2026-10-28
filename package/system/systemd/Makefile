include $(TOPDIR)/rules.mk

PKG_NAME:=systemd
PKG_VERSION:=262
PKG_RELEASE:=10
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/systemd/systemd/tar.gz/refs/tags/v$(PKG_VERSION)?
PKG_HASH:=6aa77506c0644aa67f940a48e3d3a7368601f787e4f249139516d353f107bcab
PKG_LICENSE:=LGPL-2.1-or-later
PKG_LICENSE_FILES:=LICENSES/LGPL-2.1-or-later.txt
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=python-jinja2/host
PKG_CONFIG_DEPENDS:=CONFIG_PACKAGE_libudev-systemd CONFIG_PACKAGE_systemd-udev CONFIG_PACKAGE_systemd-machined CONFIG_PACKAGE_systemd-nspawn \
	CONFIG_PACKAGE_systemd-coredump CONFIG_PACKAGE_systemd-oomd CONFIG_PACKAGE_systemd-hostnamed

MESON_USE_STAGING_PYTHON:=1
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

MESON_VARS += PATH="$(STAGING_DIR_HOSTPKG)/bin:$(TARGET_PATH)"

define Package/libsystemd
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=systemd public API library
  DEPENDS:=+libopenssl +libseccomp +libmount +libblkid
endef

define Package/systemd
  SECTION:=base
  CATEGORY:=Base system
  TITLE:=systemd system and service manager
  DEPENDS:=@OPENWRT_SYSTEMD +libsystemd +libpam +libacl +libpcre2 +mount-utils +swap-utils
  USERID:=:systemd-journal=190
endef

define Package/libudev-systemd
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=Native systemd device enumeration library
  # Preserve an unpinned legacy world selection while replacing its provider.
  PROVIDES:=libudev libudev-zero
  CONFLICTS:=libudev-zero eudev udev
  # APK does not consume the IPK Conflicts field.
  EXTRA_DEPENDS:=$(if $(CONFIG_USE_APK),!libudev-zero (>=0)$(comma) !eudev (>=0)$(comma) !udev (>=0))
endef

define Package/systemd-udev
  $(call Package/systemd/optional)
  TITLE:=Native device manager for logind desktops
  DEPENDS+=+libudev-systemd
endef

define Package/systemd/conffiles
/etc/systemd/
/etc/machine-id
endef

define Package/systemd/optional
  SECTION:=base
  CATEGORY:=Base system
  DEPENDS:=@OPENWRT_SYSTEMD +systemd
  EXTRA_DEPENDS:=systemd (=$(PKG_VERSION)-r$(PKG_RELEASE))
endef

define Package/systemd-machined
  $(call Package/systemd/optional)
  TITLE:=systemd machine registration and machinectl
endef

define Package/systemd-hostnamed
  $(call Package/systemd/optional)
  TITLE:=systemd hostname service and hostnamectl
endef

define Package/systemd-nspawn
  $(call Package/systemd/optional)
  TITLE:=systemd namespace container runner
  DEPENDS+=+systemd-machined
endef

define Package/systemd-coredump
  $(call Package/systemd/optional)
  TITLE:=systemd crash collection and coredumpctl
endef

define Package/systemd-oomd
  $(call Package/systemd/optional)
  TITLE:=systemd memory pressure monitor and oomctl
endef

MESON_ARGS += \
	--prefix=/usr --libdir=lib --libexecdir=lib/systemd \
	-Dmode=release -Dsplit-bin=true -Dlibc=glibc -Dvcs-tag=false \
	-Dauto_features=disabled -Dlibmount=enabled -Dblkid=enabled \
	-Dseccomp=enabled -Dopenssl=enabled -Dnss-systemd=true \
	-Dsysusers=true -Dtmpfiles=true -Dhwdb=false \
	-Dlogind=true -Duserdb=false -Dpam=enabled -Dpolkit=enabled -Dacl=enabled -Dlibcrypt=disabled \
	-Dpamlibdir=/usr/lib/security -Dpamconfdir=/etc/pam.d \
	-Ddefault-kill-user-processes=false \
	-Dnetworkd=false -Dresolve=false -Dtimesyncd=false -Dtimedated=false \
	-Dhostnamed=$(if $(CONFIG_PACKAGE_systemd-hostnamed),true,false) \
	-Dlocaled=false -Dmachined=$(if $(CONFIG_PACKAGE_systemd-machined),true,false) -Dportabled=false \
	-Dmountfsd=false -Dsysext=false -Dhomed=disabled -Dnsresourced=false \
	-Dcoredump=$(if $(CONFIG_PACKAGE_systemd-coredump),true,false) \
	-Doomd=$(if $(CONFIG_PACKAGE_systemd-oomd),true,false) -Dpstore=false -Drepart=disabled \
	-Dsysupdate=disabled -Dsysupdated=disabled -Dsysinstall=false \
	-Dstoragetm=false -Dimportd=disabled \
	-Dnspawn=$(if $(CONFIG_PACKAGE_systemd-nspawn),enabled,disabled) -Dvmspawn=disabled \
	-Dfirstboot=false -Dhibernate=false -Dbacklight=false -Drfkill=false \
	-Dvconsole=false -Dxdg-autostart=false -Dbinfmt=false -Dquotacheck=false \
	-Dbootloader=disabled -Dukify=disabled -Defi=false -Dtpm=false \
	-Dkernel-install=false -Dbpf-framework=disabled -Danalyze=true -Dpcre2=enabled \
	-Dtests=false -Dfuzz-tests=false -Dinstall-tests=false \
	-Dman=disabled -Dhtml=disabled -Dtranslations=false \
	-Djournal-storage-default=volatile -Dfallback-default-target=multi-user.target \
	-Ddefault-user-shell=/bin/ash -Dsystem-uid-max=999 -Dsystem-gid-max=999 \
	-Dmount-path=/usr/bin/mount -Dumount-path=/usr/bin/umount \
	-Dsulogin-path=/sbin/sulogin -Dswapon-path=/usr/sbin/swapon \
	-Dswapoff-path=/usr/sbin/swapoff

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include/systemd $(1)/usr/lib/pkgconfig
	$(INSTALL_DIR) $(1)/usr/share/pkgconfig
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/pkgconfig/systemd.pc $(1)/usr/share/pkgconfig/
	$(CP) $(PKG_INSTALL_DIR)/usr/include/systemd/*.h $(1)/usr/include/systemd/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libsystemd.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/libsystemd.pc $(1)/usr/lib/pkgconfig/
	# Keep the development metadata relocatable by OpenWrt's pkg-config wrapper.
	awk '/^libdir=/ { print "libdir=" sprintf("%c", 36) "{prefix}/lib"; next } \
		/^includedir=/ { print "includedir=" sprintf("%c", 36) "{prefix}/include"; next } \
		{ print }' $(1)/usr/lib/pkgconfig/libsystemd.pc > $(1)/usr/lib/pkgconfig/libsystemd.pc.tmp
	mv $(1)/usr/lib/pkgconfig/libsystemd.pc.tmp $(1)/usr/lib/pkgconfig/libsystemd.pc
	$(if $(CONFIG_PACKAGE_libudev-systemd),$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/include/libudev.h $(1)/usr/include/)
	$(if $(CONFIG_PACKAGE_libudev-systemd),$(CP) $(PKG_INSTALL_DIR)/usr/lib/libudev.so* $(1)/usr/lib/)
	$(if $(CONFIG_PACKAGE_libudev-systemd),$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/libudev.pc $(1)/usr/lib/pkgconfig/)
	$(if $(CONFIG_PACKAGE_systemd-udev),$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/pkgconfig/udev.pc $(1)/usr/share/pkgconfig/)
	$(if $(CONFIG_PACKAGE_libudev-systemd),awk ' \
		/^libdir=/ { print "libdir=" sprintf("%c", 36) "{prefix}/lib"; next } \
		/^includedir=/ { print "includedir=" sprintf("%c", 36) "{prefix}/include"; next } \
		{ print }' $(1)/usr/lib/pkgconfig/libudev.pc > $(1)/usr/lib/pkgconfig/libudev.pc.tmp)
	$(if $(CONFIG_PACKAGE_libudev-systemd),mv $(1)/usr/lib/pkgconfig/libudev.pc.tmp $(1)/usr/lib/pkgconfig/libudev.pc)
endef

define Package/libudev-systemd/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libudev.so.* $(1)/usr/lib/
endef

define Package/systemd-udev/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib/systemd/system $(1)/usr/lib/udev/rules.d
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/udevadm $(1)/usr/bin/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/systemd/systemd-udevd $(1)/usr/lib/systemd/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/systemd/system/systemd-udev* $(1)/usr/lib/systemd/system/
	# procd remains responsible for network names, module loading and firmware.
	# Install only desktop identification, permissions and seat rules.
	for rule in 50-udev-default 60-drm 60-input-id 60-persistent-input 60-sensor \
		60-serial 70-uaccess 71-seat 73-seat-late; do \
		[ ! -f $(PKG_INSTALL_DIR)/usr/lib/udev/rules.d/$$$$rule.rules ] || \
			$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/udev/rules.d/$$$$rule.rules $(1)/usr/lib/udev/rules.d/; \
	done
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system/sysinit.target.wants
	$(LN) ../systemd-udevd-kernel.socket $(1)/usr/lib/systemd/system/sysinit.target.wants/
	$(LN) ../systemd-udevd-control.socket $(1)/usr/lib/systemd/system/sysinit.target.wants/
endef

define Package/libsystemd/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libsystemd.so.* $(1)/usr/lib/
endef

define Package/systemd/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib $(1)/etc
	$(CP) $(PKG_INSTALL_DIR)/usr/bin/. $(1)/usr/bin/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/systemd $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/{tmpfiles.d,sysusers.d} $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libnss_systemd.so.2 $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/etc/systemd $(1)/etc/
	$(INSTALL_DIR) $(1)/usr/lib/security $(1)/etc/pam.d
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/security/pam_systemd.so $(1)/usr/lib/security/
	$(INSTALL_DATA) ./files/systemd-user.pam $(1)/etc/pam.d/systemd-user
	$(INSTALL_DIR) $(1)/usr/share/polkit-1/actions $(1)/usr/share/polkit-1/rules.d
	$(CP) $(PKG_INSTALL_DIR)/usr/share/polkit-1/actions/*.policy $(1)/usr/share/polkit-1/actions/
	$(INSTALL_DIR) $(1)/usr/share/dbus-1/system-services
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/dbus-1/system-services/org.freedesktop.login1.service \
		$(1)/usr/share/dbus-1/system-services/
	# OpenWrt owns DRM module loading.
	$(SED) 's/ modprobe@drm.service//g' \
		$(1)/usr/lib/systemd/system/systemd-logind.service
	$(INSTALL_DIR) $(1)/etc/dbus-1/system.d
	$(CP) $(PKG_INSTALL_DIR)/usr/share/dbus-1/system.d/*.conf $(1)/etc/dbus-1/system.d/
	touch $(1)/etc/machine-id
	# OpenWrt retains its own init, device-event and syslog owners.
	rm -f $(1)/usr/bin/{halt,poweroff,reboot,shutdown,init,udevadm}
	rm -f $(1)/usr/lib/systemd/systemd-udevd
	find $(1)/usr/lib/systemd/system -name 'systemd-udev*' -delete
	rm -f $(1)/usr/lib/systemd/system-generators/systemd-{getty,fstab,gpt-auto,ssh}-generator
	# Optional components own their executables, activation and configuration.
	rm -f $(1)/usr/bin/{hostnamectl,machinectl,systemd-nspawn,coredumpctl,oomctl}
	rm -f $(1)/usr/lib/systemd/{systemd-hostnamed,systemd-machined,systemd-coredump,systemd-oomd}
	find $(1)/usr/lib/systemd/system -name '*hostnamed*' -delete
	find $(1)/usr/lib/systemd/system -name '*hostname1*' -delete
	rm -f $(1)/usr/lib/systemd/system/systemd-machine-tag@.service
	find $(1)/usr/lib/systemd/system -name '*machined*' -delete
	find $(1)/usr/lib/systemd/system -name '*machine1*' -delete
	find $(1)/usr/lib/systemd/system -name '*nspawn*' -delete
	find $(1)/usr/lib/systemd/system -name '*coredump*' -delete
	find $(1)/usr/lib/systemd/system -name '*oomd*' -delete
	rm -f $(1)/usr/lib/tmpfiles.d/systemd-nspawn.conf
	rm -f $(1)/usr/lib/sysusers.d/systemd-{coredump,oom}.conf
	rm -f $(1)/etc/systemd/{coredump,oomd}.conf
	rm -f $(1)/usr/share/polkit-1/actions/org.freedesktop.{hostname1,machine1}.policy
	rm -f $(1)/etc/dbus-1/system.d/org.freedesktop.{hostname1,machine1,oom1}.conf
endef

define Package/systemd-hostnamed/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib/systemd/system \
		$(1)/etc/dbus-1/system.d $(1)/usr/share/dbus-1/system-services \
		$(1)/usr/share/polkit-1/actions
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/hostnamectl $(1)/usr/bin/
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/lib/systemd/systemd-hostnamed $(1)/usr/lib/systemd/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/systemd/system/systemd-hostnamed.* $(1)/usr/lib/systemd/system/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/systemd/system/systemd-machine-tag@.service $(1)/usr/lib/systemd/system/
	$(LN) systemd-hostnamed.service $(1)/usr/lib/systemd/system/dbus-org.freedesktop.hostname1.service
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/dbus-1/system.d/org.freedesktop.hostname1.conf $(1)/etc/dbus-1/system.d/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/dbus-1/system-services/org.freedesktop.hostname1.service $(1)/usr/share/dbus-1/system-services/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/polkit-1/actions/org.freedesktop.hostname1.policy $(1)/usr/share/polkit-1/actions/
endef

define Package/systemd-machined/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib/systemd/system $(1)/usr/lib/tmpfiles.d \
		$(1)/etc/dbus-1/system.d $(1)/usr/share/dbus-1/system-services \
		$(1)/usr/share/polkit-1/actions
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/machinectl $(1)/usr/bin/
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/lib/systemd/systemd-machined $(1)/usr/lib/systemd/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/systemd/system/systemd-machined.* $(1)/usr/lib/systemd/system/
	$(LN) systemd-machined.service $(1)/usr/lib/systemd/system/dbus-org.freedesktop.machine1.service
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/tmpfiles.d/systemd-nspawn.conf $(1)/usr/lib/tmpfiles.d/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/dbus-1/system.d/org.freedesktop.machine1.conf $(1)/etc/dbus-1/system.d/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/dbus-1/system-services/org.freedesktop.machine1.service $(1)/usr/share/dbus-1/system-services/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/polkit-1/actions/org.freedesktop.machine1.policy $(1)/usr/share/polkit-1/actions/
endef

define Package/systemd-nspawn/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib/systemd/system
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/systemd-nspawn $(1)/usr/bin/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/systemd/system/systemd-nspawn@.service $(1)/usr/lib/systemd/system/
	# OpenWrt owns module loading; configure container networking explicitly.
	$(SED) 's/modprobe@[^ ]*\.service//g; s/--network-veth/--private-network/' $(1)/usr/lib/systemd/system/systemd-nspawn@.service
endef

define Package/systemd-coredump/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib/systemd/system $(1)/usr/lib/sysusers.d
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/coredumpctl $(1)/usr/bin/
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/lib/systemd/systemd-coredump $(1)/usr/lib/systemd/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/systemd/system/systemd-coredump* $(1)/usr/lib/systemd/system/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/sysusers.d/systemd-coredump.conf $(1)/usr/lib/sysusers.d/
endef

define Package/systemd-oomd/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib/systemd/system $(1)/usr/lib/sysusers.d \
		$(1)/etc/dbus-1/system.d $(1)/usr/share/dbus-1/system-services
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/oomctl $(1)/usr/bin/
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/lib/systemd/systemd-oomd $(1)/usr/lib/systemd/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/systemd/system/systemd-oomd.* $(1)/usr/lib/systemd/system/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/sysusers.d/systemd-oom.conf $(1)/usr/lib/sysusers.d/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/dbus-1/system.d/org.freedesktop.oom1.conf $(1)/etc/dbus-1/system.d/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/dbus-1/system-services/org.freedesktop.oom1.service $(1)/usr/share/dbus-1/system-services/
endef

$(eval $(call BuildPackage,libsystemd))
$(eval $(call BuildPackage,systemd))
$(eval $(call BuildPackage,libudev-systemd))
$(eval $(call BuildPackage,systemd-udev))
$(eval $(call BuildPackage,systemd-hostnamed))
$(eval $(call BuildPackage,systemd-machined))
$(eval $(call BuildPackage,systemd-nspawn))
$(eval $(call BuildPackage,systemd-coredump))
$(eval $(call BuildPackage,systemd-oomd))
