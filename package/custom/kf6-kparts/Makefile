include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kparts
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kparts-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=9e71e3d20c9525f66533dd7a5846f0d982eefdd7425bfbadecd6a17908ebd709
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Parts
KF6_DEPENDS:=+qt6base-widgets +qt6base-xml +kf6-kconfig +kf6-kcoreaddons \
	+kf6-ki18n +kf6-kio +kf6-kjobwidgets +kf6-kservice +kf6-kwidgetsaddons \
	+kf6-kxmlgui

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
