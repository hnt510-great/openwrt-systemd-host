include $(TOPDIR)/rules.mk

PKG_NAME:=kde-cli-tools
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=2d702d018e895ecf879d5827d75944563a12ab27244f231bab6c5a40c7656c76
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=KDE CLI Tools
KF6_DEPENDS:=+qt6base-widgets +qt6svg +qt6base-dbus +kf6-kconfig +kf6-kiconthemes +kf6-ki18n +kf6-kcmutils +kf6-kio +kf6-kservice +kf6-kwindowsystem +kf6-kparts +kf6-kcoreaddons +kf6-kwidgetsaddons
KF6_CMAKE_OPTIONS:=-DBUILD_DOC=OFF -DCMAKE_DISABLE_FIND_PACKAGE_KF6DocTools=ON -DCMAKE_DISABLE_FIND_PACKAGE_KF6Su=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
