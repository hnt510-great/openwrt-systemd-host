include $(TOPDIR)/rules.mk

PKG_NAME:=polkit
PKG_VERSION:=128
PKG_RELEASE:=4
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/polkit-org/polkit/tar.gz/refs/tags/$(PKG_VERSION)?
PKG_HASH:=6edb06bf1448e49e428f9597a97af6a05d62146dd0b58f86eeaebcee3f5ecfaa
PKG_LICENSE:=LGPL-2.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk
PKG_CONFIG_DEPENDS+=CONFIG_PACKAGE_gtk4
ifneq ($(CONFIG_PACKAGE_gtk4),)
include $(INCLUDE_DIR)/gobject-introspection.mk
PKG_BUILD_DEPENDS+=glib2-gir
endif

define Package/polkit
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Native systemd authorization manager and text agent
  URL:=https://github.com/polkit-org/polkit
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +glib2-gio +libexpat +libduktape +libsystemd +libpam +dbus
  USERID:=polkitd=192:polkitd=192
endef

define Package/polkit/conffiles
/etc/polkit-1/
/etc/pam.d/polkit-1
endef

MESON_ARGS += --prefix=/usr --libdir=lib --sysconfdir=/etc \
	-Dsession_tracking=logind -Dauthfw=pam -Dos_type=lfs \
	-Dpolkitd_user=polkitd -Dpolkitd_uid=192 -Dprivileged_group=root \
	-Dsystemdsystemunitdir=/usr/lib/systemd/system \
	-Dpam_prefix=/etc/pam.d -Dpam_module_dir=/usr/lib/security \
	-Dintrospection=$(if $(CONFIG_PACKAGE_gtk4),true,false) -Dexamples=false -Dtests=false \
	-Dgtk_doc=false -Dman=false -Dgettext=false -Ddefault_library=shared

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/polkit-1 $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libpolkit*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/polkit*.pc $(1)/usr/lib/pkgconfig/
	$(INSTALL_DIR) $(1)/usr/share/gettext/its
	$(CP) $(PKG_INSTALL_DIR)/usr/share/gettext/its/. $(1)/usr/share/gettext/its/
ifneq ($(CONFIG_PACKAGE_gtk4),)
	$(INSTALL_DIR) $(1)/usr/share/gir-1.0 $(1)/usr/lib/girepository-1.0
	$(CP) $(PKG_INSTALL_DIR)/usr/share/gir-1.0/. $(1)/usr/share/gir-1.0/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/. $(1)/usr/lib/girepository-1.0/
endif
endef

define Package/polkit/install
	$(INSTALL_DIR) $(1)/usr/lib/polkit-1 $(1)/usr/bin $(1)/usr/share
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libpolkit*.so.* $(1)/usr/lib/
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/lib/polkit-1/polkitd $(1)/usr/lib/polkit-1/
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/lib/polkit-1/polkit-agent-helper-1 $(1)/usr/lib/polkit-1/
	chmod 4755 $(1)/usr/lib/polkit-1/polkit-agent-helper-1
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/pkcheck $(PKG_INSTALL_DIR)/usr/bin/pkaction \
		$(PKG_INSTALL_DIR)/usr/bin/pkttyagent $(1)/usr/bin/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/dbus-1 $(1)/usr/share/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/polkit-1 $(1)/usr/share/
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system $(1)/etc/polkit-1/rules.d $(1)/etc/pam.d
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/systemd/system/polkit.service $(1)/usr/lib/systemd/system/
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system/polkit.service.d
	$(INSTALL_DATA) ./files/polkit-service.conf $(1)/usr/lib/systemd/system/polkit.service.d/openwrt.conf
	$(INSTALL_DATA) ./files/polkit-1 $(1)/etc/pam.d/polkit-1
	$(INSTALL_DIR) $(1)/usr/share/gettext/its
	$(CP) $(PKG_INSTALL_DIR)/usr/share/gettext/its/. $(1)/usr/share/gettext/its/
	$(INSTALL_DATA) ./files/10-openwrt-admin.rules $(1)/usr/share/polkit-1/rules.d/
ifneq ($(CONFIG_PACKAGE_gtk4),)
	$(INSTALL_DIR) $(1)/usr/lib/girepository-1.0
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/girepository-1.0/. $(1)/usr/lib/girepository-1.0/
endif
endef

$(eval $(call BuildPackage,polkit))
