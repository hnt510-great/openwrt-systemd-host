include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kunitconversion
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kunitconversion-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=af5e72a5cf7ee3d036e045441fc84a5e9c142be6d46bd36c1490d1cec5e7ecfd
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KUnitConversion
KF6_DEPENDS:=+qt6base-core +qt6base-network +kf6-ki18n

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
