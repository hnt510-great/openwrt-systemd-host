include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kholidays
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kholidays-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=a6aeede0b1c5bba93f7e60d7c6fe84051cb32d90d3981202c4f90237b5fc17a7
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KHolidays
KF6_DEPENDS:=+qt6base-core +qt6quick-qml

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
