include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-karchive
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=karchive-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=30687d9be0aea05a4ef887212abd91d7c4337cb9f166610f98eac2b01407fb1f
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Archive
KF6_DEPENDS:=+qt6base-core +zlib +bzip2 +liblzma +libopenssl

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
