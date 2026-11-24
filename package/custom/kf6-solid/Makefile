include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-solid
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=solid-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=9620a6065403c5097fce0518abb7d4f038f4f11327e7ce94094ae9561bce0008
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Solid device integration
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-xml +qt6base-dbus +libudev \
	+libmount
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
