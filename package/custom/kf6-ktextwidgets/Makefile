include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-ktextwidgets
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=ktextwidgets-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=781e7fad5720de7f31380b2c4a458bc2875940449ed9168b48c60d474b6df220
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Text Widgets
KF6_DEPENDS:=+qt6base-widgets +kf6-kcompletion +kf6-kconfig +kf6-ki18n \
	+kf6-kwidgetsaddons +kf6-sonnet +qt6speech

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
