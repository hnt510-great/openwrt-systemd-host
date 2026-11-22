include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-sonnet
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=sonnet-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=356cddaf7cf2aabcaf850314bb248fa56a15b8285fea74d8f3a7c7e4dec2a83a
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Sonnet spell checking
KF6_DEPENDS:=+qt6base-core +qt6base-widgets +zlib +hunspell +hunspell-en
# The QML bindings need Qt Quick, which this tree does not build. Hunspell is
# found through its pkg-config file and provides the spell-check backend.
KF6_CMAKE_OPTIONS:=-DSONNET_USE_QML=OFF

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
