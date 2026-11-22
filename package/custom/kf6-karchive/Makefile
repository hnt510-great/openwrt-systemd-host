include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-karchive
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=karchive-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=f6a508d537d283e2a106e848a939e971cdf1a059779825e4482609aa981ffadd
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Archive
KF6_DEPENDS:=+qt6base-core +zlib +bzip2 +liblzma +libopenssl

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
