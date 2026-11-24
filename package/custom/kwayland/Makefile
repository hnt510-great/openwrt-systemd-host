include $(TOPDIR)/rules.mk

PKG_NAME:=kwayland
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=00090254b86f1774e296b4dc7d69d073ee08efb75419c9b5d0955eeae0378a56
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=KWayland
KF6_DEPENDS:=+qt6base-gui +qt6base-concurrent +qt6waylandclient +libwayland +libmesa
PKG_BUILD_DEPENDS:=wayland wayland-protocols plasma-wayland-protocols

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
