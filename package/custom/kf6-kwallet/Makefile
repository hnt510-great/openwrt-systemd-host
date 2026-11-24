include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kwallet
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kwallet-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=d68f74617519d1ebc88f152c29d51333f600b9f0aa8757c0a4fe49a40a5107fa
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KWallet (client library)
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-widgets +qt6base-dbus +kf6-kconfig
KF6_CMAKE_OPTIONS:=-DBUILD_KSECRETD=OFF -DBUILD_KWALLETD=OFF -DBUILD_KWALLET_QUERY=OFF -DCMAKE_DISABLE_FIND_PACKAGE_KF6DocTools=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
