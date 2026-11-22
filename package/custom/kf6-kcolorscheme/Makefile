include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kcolorscheme
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kcolorscheme-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=1505acc69b2cc1be9ad325a70ab9669bb8d316fc5d601ccf4032be22fab8c0c2
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Color Scheme
KF6_DEPENDS:=+qt6base-gui +kf6-kconfig +kf6-kguiaddons +kf6-ki18n

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
