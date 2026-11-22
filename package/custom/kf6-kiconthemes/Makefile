include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kiconthemes
PKG_VERSION:=6.20.0
PKG_RELEASE:=2
PKG_SOURCE:=kiconthemes-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=61b906051cd66db1dd259ec76d08885d3fe749e0d3947aea749021d2c96537a5
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Icon Themes
KF6_DEPENDS:=+qt6base-widgets +qt6base-dbus +qt6svg +kf6-karchive +kf6-ki18n \
	+kf6-kwidgetsaddons +kf6-kcolorscheme +kf6-breeze-icons
PKG_BUILD_DEPENDS:=kf6-breeze-icons
KF6_CMAKE_OPTIONS:=-DKICONTHEMES_USE_QTQUICK=OFF -DUSE_BreezeIcons=ON -DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
