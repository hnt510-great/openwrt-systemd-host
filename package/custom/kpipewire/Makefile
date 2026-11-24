include $(TOPDIR)/rules.mk

PKG_NAME:=kpipewire
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=6b3175c928322e2084f8c40e51c05c24e3823b05195ff6de7db27c130a19c12f
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=KPipeWire
KF6_DEPENDS:=+qt6base-dbus +qt6base-opengl +qt6quick +kf6-ki18n +kf6-kcoreaddons +libmesa +libepoxy +libdrm +pipewire +libffmpeg +libva
PKG_BUILD_DEPENDS:=plasma-wayland-protocols mesa libepoxy libdrm pipewire ffmpeg libva

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
