include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-prison
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=prison-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=13d904f7514ffe32e49fe09a2b5e10125f825d42c26ee52294c15ce1bfab3970
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Prison
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6quick +libqrencode
KF6_CMAKE_OPTIONS:=-DWITH_DMTX=OFF -DWITH_ZXING=OFF -DWITH_MULTIMEDIA=OFF

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
