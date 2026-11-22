include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kcompletion
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kcompletion-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=3b270003b661db894f50e9f90fdddd309c3ea97010e363bc551f752db6efcecc
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Completion
KF6_DEPENDS:=+qt6base-widgets +kf6-kcodecs +kf6-kconfig +kf6-kwidgetsaddons

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
