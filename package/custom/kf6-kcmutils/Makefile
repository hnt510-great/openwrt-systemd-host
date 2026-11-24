include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kcmutils
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kcmutils-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=473395787e6921d37298e191cc1718f8818f630b98bdf312583ad25606f6a09e
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.0-or-later LGPL-3.0-only

KF6_TITLE:=KCM Utilities
KF6_DEPENDS:=+qt6base-dbus +qt6quick-widgets +kf6-kconfigwidgets \
	+kf6-kcoreaddons +kf6-kguiaddons +kf6-ki18n +kf6-kio +kf6-kirigami \
	+kf6-kitemviews +kf6-kwidgetsaddons +kf6-kxmlgui

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
