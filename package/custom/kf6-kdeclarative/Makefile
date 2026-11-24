include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kdeclarative
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kdeclarative-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=9e187056b3e1d49ecde29b30e4a4f5f2633639b622dd596369eac86c45c7f167
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KDeclarative
KF6_DEPENDS:=+qt6base-gui +qt6base-widgets +qt6quick +kf6-kconfig +kf6-kglobalaccel +kf6-kguiaddons +kf6-ki18n +kf6-kwidgetsaddons

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
