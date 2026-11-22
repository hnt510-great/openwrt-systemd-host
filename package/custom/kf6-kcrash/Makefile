include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kcrash
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kcrash-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=1f42e9c54ead9f2d81b3ec5eacf55ab6ff4dd1c3a0721c68f3ab39ed46f35973
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Crash Handler
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-test +libX11 +kf6-kcoreaddons
KF6_CMAKE_OPTIONS:=-DWITH_X11=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
