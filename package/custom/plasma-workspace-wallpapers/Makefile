include $(TOPDIR)/rules.mk

PKG_NAME:=plasma-workspace-wallpapers
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=fa4ff783f41c8fa08a58d32f094d7acc6c5ac268e23354bd49a40a35617463d6
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=Plasma Workspace Wallpapers
KF6_DEPENDS:=

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
