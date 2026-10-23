include $(TOPDIR)/rules.mk
PKG_NAME:=virt-manager
PKG_VERSION:=5.1.0
PKG_RELEASE:=3
PKG_SOURCE:=virt-manager-5.1.0.tar.xz
PKG_SOURCE_URL:=https://github.com/virt-manager/virt-manager/releases/download/v5.1.0/
PKG_HASH:=ccfc44b6c1c0be8398beb687c675d9ea4ca1c721dfb67bd639209a7b0dec11b1
PKG_LICENSE:=GPL-2.0-or-later
PKG_INSTALL:=1
PKG_BUILD_DEPENDS:=python3/host python-docutils/host glib2/host
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk
MESON_USE_STAGING_PYTHON:=1
PYTHON_BIN:=$(STAGING_DIR_HOSTPKG)/bin/python3
MESON_VARS += PATH="$(STAGING_DIR_HOSTPKG)/bin:$(TARGET_PATH)"
MESON_ARGS += -Ddefault-hvs=qemu -Ddefault-graphics=spice -Dupdate-icon-cache=false -Dcompile-schemas=false -Dtests=disabled

define Package/virt-manager-common
  SECTION:=utils
  CATEGORY:=Utilities
  SUBMENU:=Virtualization
  TITLE:=Shared virtual machine creation libraries
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +python3 +python3-gobject +python3-libvirt +python3-libxml2 +python3-requests +python3-argcomplete +libosinfo +osinfo-db +xorriso
endef

define Package/virt-install
  $(call Package/virt-manager-common)
  TITLE:=Virtual machine installation command line tools
  DEPENDS:=+virt-manager-common +virsh
endef

define Package/virt-manager
  $(call Package/virt-manager-common)
  TITLE:=Virtual Machine Manager for the Weston desktop
  DEPENDS:=+virt-manager-common +libgtk3 +gtk-vnc +spice-gtk +accel-support +libvirt-glib +libvte3 +dconf +glib2-utils +libvirt-daemon +openwrt-desktop +shadow-groupadd +shadow-gpasswd
endef

define Package/virt-manager/conffiles
/etc/libvirt/desktop-access
endef

define Package/virt-manager-common/install
	$(INSTALL_DIR) $(1)/usr/share/virt-manager
	$(CP) $(PKG_INSTALL_DIR)/usr/share/virt-manager/virtinst $(1)/usr/share/virt-manager/
endef

define Package/virt-install/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/virt-install $(PKG_INSTALL_DIR)/usr/bin/virt-clone $(PKG_INSTALL_DIR)/usr/bin/virt-xml $(1)/usr/bin/
endef

define Package/virt-manager/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/sbin $(1)/usr/libexec $(1)/usr/share/virt-manager $(1)/usr/share/icons $(1)/usr/share/applications $(1)/usr/share/glib-2.0/schemas $(1)/lib/upgrade/keep.d
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/virt-manager $(1)/usr/bin/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/virt-manager/virtManager $(PKG_INSTALL_DIR)/usr/share/virt-manager/ui $(PKG_INSTALL_DIR)/usr/share/virt-manager/icons $(1)/usr/share/virt-manager/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/icons/. $(1)/usr/share/icons/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/applications/virt-manager.desktop $(1)/usr/share/applications/
	$(SED) 's|^Exec=.*|Exec=/usr/libexec/virt-manager-launch|' $(1)/usr/share/applications/virt-manager.desktop
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/glib-2.0/schemas/*.xml $(1)/usr/share/glib-2.0/schemas/
	$(INSTALL_BIN) ./files/virt-manager-setup $(1)/usr/sbin/
	$(INSTALL_BIN) ./files/virt-manager-launch $(1)/usr/libexec/
	$(INSTALL_DATA) ./files/virt-manager.keep $(1)/lib/upgrade/keep.d/virt-manager
endef

define Package/virt-manager/postinst
#!/bin/sh
[ -n "$$IPKG_INSTROOT" ] || /usr/libexec/glib2-cache-update
exit 0
endef
$(eval $(call BuildPackage,virt-manager-common))
$(eval $(call BuildPackage,virt-install))
$(eval $(call BuildPackage,virt-manager))
