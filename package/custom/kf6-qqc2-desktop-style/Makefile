include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-qqc2-desktop-style
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=qqc2-desktop-style-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=57269c662c25d0ccea96e128a54bc57c3abe0b6b97ef586ea1195c147afc3a38
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=QQC2 Desktop Style
KF6_DEPENDS:=+qt6base-gui +qt6base-widgets +qt6quick +qt6quick-controls2 +kf6-kcolorscheme +kf6-kconfig +kf6-kiconthemes +kf6-kirigami +kf6-sonnet

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
