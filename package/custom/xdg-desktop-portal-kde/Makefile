include $(TOPDIR)/rules.mk

PKG_NAME:=xdg-desktop-portal-kde
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=d7d695716ea101a76dbfccc2b97c07058b9caaa7bbbf8ad96a3ba6fcee84a109
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=KDE XDG Desktop Portal backend
KF6_DEPENDS:=+qt6base-core +qt6base-concurrent +qt6base-dbus +qt6base-printsupport +qt6quick-widgets +qt6base-widgets +qt6waylandclient +qt6quick +qt6quick-controls2 +kf6-kcoreaddons +kf6-kconfig +kf6-ki18n +kf6-kglobalaccel +kf6-kio +kf6-kirigami +kf6-knotifications +kf6-kservice +kf6-kwidgetsaddons +kf6-kwindowsystem +kf6-kiconthemes +kf6-kstatusnotifieritem +kf6-kcrash +kwayland +kpipewire +libwayland +libxkbcommon +pipewire +xdg-desktop-portal
PKG_BUILD_DEPENDS:=kf6-kconfig/host wayland wayland-protocols plasma-wayland-protocols
KF6_CMAKE_OPTIONS:=-DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake"

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
