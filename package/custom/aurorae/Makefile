include $(TOPDIR)/rules.mk

PKG_NAME:=aurorae
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=cb9f38c36f32587a2821ec539974243d85f9c82909b8e4618b8fffd33761d299
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=Aurorae window decorations
KF6_DEPENDS:=+qt6base-core +qt6base-dbus +qt6base-widgets +qt6quick +qt6tools +kf6-kcolorscheme +kf6-kconfig +kf6-kcoreaddons +kf6-ki18n +kf6-kcmutils +kf6-knewstuff +kf6-kpackage +kf6-ksvg +kdecoration
PKG_BUILD_DEPENDS:=qt6tools

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
