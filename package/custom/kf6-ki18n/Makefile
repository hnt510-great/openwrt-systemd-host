include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-ki18n
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=ki18n-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=f29c805137af9cee6abab424b380fea964a59b089f90fb909601d9fc78df5f73
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=gettext-full/host

KF6_TITLE:=I18n
KF6_DEPENDS:=+qt6base-core +qt6base-widgets +qt6quick +iso-codes
# KNewStuff's widgets link KF6::I18nQml.
KF6_CMAKE_OPTIONS:=-DBUILD_WITH_QML=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
