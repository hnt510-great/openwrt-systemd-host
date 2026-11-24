include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kitemmodels
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kitemmodels-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=3a280dbdfc0733ffc9607897109b70b57af89c81dfca534ab92efb948eab3179
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=KItemModels
KF6_DEPENDS:=+qt6base-core +qt6quick-qml

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
