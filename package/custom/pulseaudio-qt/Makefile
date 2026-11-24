include $(TOPDIR)/rules.mk

PKG_NAME:=pulseaudio-qt
PKG_VERSION:=1.9.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/pulseaudio-qt/
PKG_HASH:=c2aace3ac1a9c8c9b9c57ba0ffc99a3d310737cc004db0491802e03536e27c69
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=PulseAudio Qt6 bindings
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-dbus +libpulse +libpulse-mainloop-glib +glib2
PKG_BUILD_DEPENDS:=pulseaudio glib2

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
