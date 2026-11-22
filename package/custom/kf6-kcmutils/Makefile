include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kcmutils
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kcmutils-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=a2d726c7b6b8feaddff29dc0e75e1c15467f02d1ebe6f8e96f35cd84b23e16ed
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.0-or-later LGPL-3.0-only

KF6_TITLE:=KCM Utilities
KF6_DEPENDS:=+qt6base-dbus +qt6quick-widgets +kf6-kconfigwidgets \
	+kf6-kcoreaddons +kf6-kguiaddons +kf6-ki18n +kf6-kio +kf6-kirigami \
	+kf6-kitemviews +kf6-kwidgetsaddons +kf6-kxmlgui

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
