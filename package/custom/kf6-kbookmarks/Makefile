include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kbookmarks
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kbookmarks-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=3967d390155e7183dd5de0087aa4bb12264958331ac18a1f8c405a5edbdc1a14
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Bookmarks
KF6_DEPENDS:=+qt6base-widgets +qt6base-xml +kf6-kconfig +kf6-kcoreaddons \
	+kf6-kwidgetsaddons

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
