include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kiconthemes
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kiconthemes-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=1bd4fe3246af5527c136afc650703e5231b8b2de32ca1eac48fa310adece8db8
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Icon Themes
KF6_DEPENDS:=+qt6base-widgets +qt6base-dbus +qt6quick +qt6svg +kf6-karchive +kf6-ki18n \
	+kf6-kwidgetsaddons +kf6-kcolorscheme +kf6-breeze-icons
PKG_BUILD_DEPENDS:=kf6-breeze-icons
KF6_CMAKE_OPTIONS:=-DKICONTHEMES_USE_QTQUICK=ON -DUSE_BreezeIcons=ON -DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
