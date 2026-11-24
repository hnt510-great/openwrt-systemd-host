include $(TOPDIR)/rules.mk

PKG_NAME:=kglobalacceld
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=e0fa8b3d951e85d1713e92f4d5c0622a5b0cd441a50383b8b26ac25cceab45c6
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=KGlobalAccelD
KF6_DEPENDS:=+qt6base-gui +qt6base-dbus +kf6-kconfig +kf6-kcoreaddons +kf6-kglobalaccel +kf6-kservice +kf6-kio +kf6-kjobwidgets

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
