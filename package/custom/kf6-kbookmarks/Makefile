include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kbookmarks
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kbookmarks-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=a796db0d6f91bd8795ef3319f85f75074d76be315119335c339cf37c1552a472
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Bookmarks
KF6_DEPENDS:=+qt6base-widgets +qt6base-xml +kf6-kconfig +kf6-kcoreaddons \
	+kf6-kwidgetsaddons

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
