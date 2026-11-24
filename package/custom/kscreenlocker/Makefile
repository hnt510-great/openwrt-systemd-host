include $(TOPDIR)/rules.mk

PKG_NAME:=kscreenlocker
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=03c61481bb8934c6beaf8f8dd986d2679c0f59f8336e548d85f0872b767edf01
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=KScreenLocker
KF6_DEPENDS:=+qt6base-dbus +qt6base-widgets +qt6quick +kf6-kcrash +kf6-kcmutils +kf6-kio +kf6-kglobalaccel +kf6-ki18n +kf6-kidletime +kf6-knotifications +kf6-solid +kf6-kwindowsystem +kf6-kxmlgui +kf6-ksvg +libplasma +layer-shell-qt +libkscreen +libpam +libxcb +libxcb-keysyms
PKG_BUILD_DEPENDS:=kf6-kconfig/host libpam wayland wayland-protocols
KF6_CMAKE_OPTIONS:=-DPAM_INCLUDE_DIR="$(STAGING_DIR)/usr/include" -DPAM_LIBRARY="$(STAGING_DIR)/usr/lib/libpam.so" -DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake"

include $(INCLUDE_DIR)/kf6-package.mk

define Package/kscreenlocker/conffiles
/etc/pam.d/kde
endef

define Package/kscreenlocker/install
	[ ! -d $(PKG_INSTALL_DIR)/usr ] || $(CP) $(PKG_INSTALL_DIR)/usr $(1)/
	[ ! -d $(PKG_INSTALL_DIR)/etc ] || $(CP) $(PKG_INSTALL_DIR)/etc $(1)/
	$(INSTALL_DIR) $(1)/etc/pam.d
	$(INSTALL_DATA) ./files/kde.pam $(1)/etc/pam.d/kde
	$(RM) -r $(1)/usr/include $(1)/usr/lib/cmake $(1)/usr/lib/pkgconfig \
		$(1)/usr/share/doc $(1)/usr/share/man
	find $(1) -type f \( -name '*.a' -o -name '*.la' \) -delete
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
