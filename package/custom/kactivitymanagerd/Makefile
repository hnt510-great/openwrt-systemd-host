include $(TOPDIR)/rules.mk

PKG_NAME:=kactivitymanagerd
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=ace8726d6a3f95769dd3c8614d4c0a432ce756bd60ab12584b2d13280db471f1
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later
CMAKE_BINARY_SUBDIR:=build

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=KActivityManagerD
KF6_DEPENDS:=+qt6base-core +qt6base-dbus +qt6base-widgets +qt6base-sql +qt6base-plugin-sqldrivers-sqlite +kf6-kdbusaddons +kf6-ki18n +kf6-kcrash +kf6-kio +kf6-kconfig +kf6-kcoreaddons +kf6-kglobalaccel +kf6-kservice +kf6-kwindowsystem +kf6-kxmlgui
PKG_BUILD_DEPENDS:=boost

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
