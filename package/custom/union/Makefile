include $(TOPDIR)/rules.mk

PKG_NAME:=union
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=cebe4d33d23ee3125191ea11130db41f19d4fb9d82fea8c50518906a7ca5279a
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=Union styling framework
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-widgets +qt6base-dbus +qt6svg +qt6quick +qt6quick-controls2 +kf6-kirigami +kf6-kcoreaddons +kf6-kguiaddons +kf6-kconfig +kf6-kiconthemes +kf6-kcolorscheme +kf6-karchive +libplasma +zlib
PKG_BUILD_DEPENDS:=qt6shadertools
KF6_CMAKE_OPTIONS:=-DBUILD_INPUT_CSS=OFF -DBUILD_INPUT_PLASMASVG=OFF -DBUILD_TOOLS=OFF

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
