include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-ki18n
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=ki18n-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=b574b381e7510cf3b14d6a16f6ed5670220f10df7f2494c21a579d20ca1d017f
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=gettext-full/host

KF6_TITLE:=I18n
KF6_DEPENDS:=+qt6base-core +qt6base-widgets +qt6quick +iso-codes
# KNewStuff's widgets link KF6::I18nQml.
KF6_CMAKE_OPTIONS:=-DBUILD_WITH_QML=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
