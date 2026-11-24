include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kparts
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kparts-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=f2e437b038a0b0b3c40f0dfc81eb5689542c2d4e1f6025436a29e17f11caa79d
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Parts
KF6_DEPENDS:=+qt6base-widgets +qt6base-xml +kf6-kconfig +kf6-kcoreaddons \
	+kf6-ki18n +kf6-kio +kf6-kjobwidgets +kf6-kservice +kf6-kwidgetsaddons \
	+kf6-kxmlgui

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
