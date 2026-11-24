include $(TOPDIR)/rules.mk

PKG_NAME:=layer-shell-qt
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=af3e56be10eb95a5993600449d6c811a08d491f7905c40a1203040b5baf98f9e
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=LayerShellQt
KF6_DEPENDS:=+qt6base-gui +qt6quick-qml +qt6waylandclient +libwayland +libxkbcommon
PKG_BUILD_DEPENDS:=wayland wayland-protocols

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
