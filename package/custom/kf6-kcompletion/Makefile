include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kcompletion
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kcompletion-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=1ec8c0f952af1b18b07c30265610c220acadf429ef1a16558d2c64679b93dcc7
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Completion
KF6_DEPENDS:=+qt6base-widgets +kf6-kcodecs +kf6-kconfig +kf6-kwidgetsaddons

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
