include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kded
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kded-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=eade144d1e197b883529f7e262035134d7ff46b859d0beff34ab778cb5ef683b
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KDED
KF6_DEPENDS:=+qt6base-core +qt6base-dbus +kf6-kconfig +kf6-kcoreaddons +kf6-kcrash +kf6-kdbusaddons +kf6-kservice
KF6_CMAKE_OPTIONS:=-DCMAKE_DISABLE_FIND_PACKAGE_KF6DocTools=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
