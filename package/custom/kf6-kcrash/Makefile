include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kcrash
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kcrash-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=fe627df1797fa92a24e53a7f33de07111c7556070028d39f258035a0c3bdb5df
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Crash Handler
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-test +libX11 +kf6-kcoreaddons
KF6_CMAKE_OPTIONS:=-DWITH_X11=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
