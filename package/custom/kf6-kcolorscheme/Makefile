include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kcolorscheme
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kcolorscheme-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=235c73afa46669c41cbe2e3a14c5a6ae1f8ad8cbb386b3f65261f65449d2b915
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Color Scheme
KF6_DEPENDS:=+qt6base-gui +kf6-kconfig +kf6-kguiaddons +kf6-ki18n

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
