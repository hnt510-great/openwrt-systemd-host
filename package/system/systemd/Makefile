include $(TOPDIR)/rules.mk

PKG_NAME:=systemd
PKG_VERSION:=262
PKG_RELEASE:=4
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/systemd/systemd/tar.gz/refs/tags/v$(PKG_VERSION)?
PKG_HASH:=6aa77506c0644aa67f940a48e3d3a7368601f787e4f249139516d353f107bcab
PKG_LICENSE:=LGPL-2.1-or-later
PKG_LICENSE_FILES:=LICENSES/LGPL-2.1-or-later.txt
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=python-jinja2/host

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

define Package/systemd/conffiles
/etc/systemd/
/etc/machine-id
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
	-Dhostnamed=false -Dlocaled=false -Dmachined=false -Dportabled=false \
	-Dmountfsd=false -Dsysext=false -Dhomed=disabled -Dnsresourced=false \
	-Dcoredump=false -Doomd=false -Dpstore=false -Drepart=disabled \
	-Dsysupdate=disabled -Dsysupdated=disabled -Dsysinstall=false \
	-Dstoragetm=false -Dimportd=disabled -Dnspawn=disabled -Dvmspawn=disabled \
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
	$(CP) $(PKG_INSTALL_DIR)/usr/include/systemd/*.h $(1)/usr/include/systemd/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libsystemd.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/libsystemd.pc $(1)/usr/lib/pkgconfig/
	# Keep the development metadata relocatable by OpenWrt's pkg-config wrapper.
	awk '/^libdir=/ { print "libdir=" sprintf("%c", 36) "{prefix}/lib"; next } \
		/^includedir=/ { print "includedir=" sprintf("%c", 36) "{prefix}/include"; next } \
		{ print }' $(1)/usr/lib/pkgconfig/libsystemd.pc > $(1)/usr/lib/pkgconfig/libsystemd.pc.tmp
	mv $(1)/usr/lib/pkgconfig/libsystemd.pc.tmp $(1)/usr/lib/pkgconfig/libsystemd.pc
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
	rm -f $(1)/usr/lib/systemd/system-generators/systemd-{getty,fstab,gpt-auto,ssh}-generator
endef

$(eval $(call BuildPackage,libsystemd))
$(eval $(call BuildPackage,systemd))
