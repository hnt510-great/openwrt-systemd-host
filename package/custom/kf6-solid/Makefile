include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-solid
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=solid-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=0328381845a11cfcfa8c18c8d60c9df7b85a07bcd7b1bd36b71c7eb3cc3492d6
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Solid device integration
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-xml +qt6base-dbus +libudev \
	+libmount
KF6_CMAKE_OPTIONS:=-DUSE_DBUS=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
