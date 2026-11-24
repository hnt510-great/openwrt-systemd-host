include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-ktextwidgets
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=ktextwidgets-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=7d8bf911d600bd695d2c9a9bdd0ff26e40092195aa18926adf89aef46a330e84
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Text Widgets
KF6_DEPENDS:=+qt6base-widgets +kf6-kcompletion +kf6-kconfig +kf6-ki18n \
	+kf6-kwidgetsaddons +kf6-sonnet +qt6speech

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
