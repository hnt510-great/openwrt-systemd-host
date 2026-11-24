include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kwidgetsaddons
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kwidgetsaddons-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=53b2f5a65df51be4c15ed14c936aad480ab3e3425a4ea6ed95897ee48e173de9
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Widgets Addons
KF6_DEPENDS:=+qt6base-widgets

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
