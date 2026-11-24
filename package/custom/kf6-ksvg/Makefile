include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-ksvg
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=ksvg-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=8299498d46373a84811d29415f9e5a115f491bd7b5fa11c1648fc36ca9374ad6
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KSvg
KF6_DEPENDS:=+qt6base-gui +qt6svg +qt6quick +kf6-karchive +kf6-kcolorscheme +kf6-kconfig +kf6-kcoreaddons +kf6-kguiaddons +kf6-kirigami
PKG_BUILD_DEPENDS:=qt6shadertools

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
