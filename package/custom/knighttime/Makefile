include $(TOPDIR)/rules.mk

PKG_NAME:=knighttime
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=b364a57af1a629d5e09c36a3c859075f8eafa2463201959548fbc362987d7c5f
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=KNightTime
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-dbus +qt6positioning +kf6-kconfig +kf6-kcoreaddons +kf6-kdbusaddons +kf6-kholidays +kf6-ki18n
PKG_BUILD_DEPENDS:=kf6-kconfig/host

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
