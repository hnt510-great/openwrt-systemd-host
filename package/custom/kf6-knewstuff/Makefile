include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-knewstuff
PKG_VERSION:=6.20.0
PKG_RELEASE:=2
PKG_SOURCE:=knewstuff-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=49443add4f1caace2e64fe7dcbe4cf78cd6b692bf0c77ba01082c82761dfa2b9
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=NewStuff
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-widgets +qt6base-xml \
	+qt6base-network +qt6base-dbus +qt6quick +qt6quick-widgets \
	+kf6-attica +kf6-karchive +kf6-kconfig +kf6-kcoreaddons +kf6-ki18n \
	+kf6-kcmutils +kf6-kirigami +kf6-kpackage +kf6-kwidgetsaddons
# Syndication is only used by the optional OPDS provider.
KF6_CMAKE_OPTIONS:=-DBUILD_DESIGNERPLUGIN=OFF \
	-DCMAKE_DISABLE_FIND_PACKAGE_KF6Syndication=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
