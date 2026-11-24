include $(TOPDIR)/rules.mk

PKG_NAME:=kscreen
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=866dead8b6bb3f974a64f18c930e219b358118213e510fcdaabafc37ee7a8a73
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=KScreen display management
KF6_DEPENDS:=+qt6base-gui +qt6quick-controls2 +qt6waylandclient +kf6-kconfig +kf6-kdbusaddons +kf6-ki18n +kf6-kcmutils +kf6-ksvg +kf6-kxmlgui +kf6-kcrash +kf6-kimageformats +libkscreen +libplasma +plasma5support +layer-shell-qt
PKG_BUILD_DEPENDS:=kf6-kconfig/host wayland-protocols
KF6_CMAKE_OPTIONS:=-DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake"

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
