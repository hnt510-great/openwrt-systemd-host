include $(TOPDIR)/rules.mk

PKG_NAME:=breeze
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=1d47a61f9f397f212d7a23d7ed7a7289b026757a050610304bb945dc067937e2
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=Breeze theme and decoration
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-widgets +qt6base-dbus +qt6svg +qt6quick +kf6-kcoreaddons +kf6-kcolorscheme +kf6-kconfig +kf6-kguiaddons +kf6-ki18n +kf6-kiconthemes +kf6-kwindowsystem +kf6-frameworkintegration +kf6-kcmutils +kdecoration
PKG_BUILD_DEPENDS:=kf6-kconfig/host
KF6_CMAKE_OPTIONS:=-DBUILD_QT5=OFF -DBUILD_QT6=ON -DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake"

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
