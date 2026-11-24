include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kquickcharts
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kquickcharts-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=9f676e504f73fa43e394833e514522baac3f3ca2b8c63908eef7f6bdf1053046
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KQuickCharts
KF6_DEPENDS:=+qt6base-gui +qt6quick +qt6quick-controls2
PKG_BUILD_DEPENDS:=qt6shadertools

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
