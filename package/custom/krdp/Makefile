include $(TOPDIR)/rules.mk

PKG_NAME:=krdp
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=8a80e5a5e0f3e7b665752a60264ac36367431d6d8865cd5797370010a819a40b
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=KRdp Remote Desktop Server
KF6_DEPENDS:=+qt6base-core +qt6base-concurrent +qt6quick +qt6base-gui +qt6base-network +qt6base-dbus +qt6waylandclient +kf6-kconfig +kf6-kdbusaddons +kf6-kcmutils +kf6-ki18n +kf6-kcoreaddons +kf6-kstatusnotifieritem +kf6-kcrash +kf6-kguiaddons +kirigami-addons +libfreerdp3 +libwinpr3 +kpipewire +libxkbcommon +qtkeychain-qt6 +libpam +libei +libsystemd +pipewire
PKG_BUILD_DEPENDS:=kf6-kconfig/host freerdp plasma-wayland-protocols libei libpam
KF6_CMAKE_OPTIONS:=-DBUILD_EXAMPLES=OFF -DPAM_INCLUDE_DIR="$(STAGING_DIR)/usr/include" -DPAM_LIBRARY="$(STAGING_DIR)/usr/lib/libpam.so" -DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake"

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
