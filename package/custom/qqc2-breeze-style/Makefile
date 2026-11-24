include $(TOPDIR)/rules.mk

PKG_NAME:=qqc2-breeze-style
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=73501d76471781d1205c6f8e094cadbe9d65443de34246a218a1a802771a9d45
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later
CMAKE_BINARY_SUBDIR:=build

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=QQC2 Breeze Style
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-dbus +qt6quick +qt6quick-controls2 +qt6quick-templates2 +kf6-kguiaddons +kf6-kconfig +kf6-kirigami +kf6-kcolorscheme +kf6-kiconthemes +libX11
PKG_BUILD_DEPENDS:=qt6shadertools

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
