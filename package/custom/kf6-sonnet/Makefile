include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-sonnet
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=sonnet-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=cae2686b18f41bde6494f353e1dccc5f045e9748b63175a9ff539b3bc93466f1
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Sonnet spell checking
KF6_DEPENDS:=+qt6base-core +qt6base-widgets +qt6base-opengl +qt6quick +zlib +hunspell +hunspell-en
KF6_CMAKE_OPTIONS:=-DSONNET_USE_QML=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
