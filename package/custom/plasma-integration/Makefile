include $(TOPDIR)/rules.mk

PKG_NAME:=plasma-integration
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=e32e074d79159f584c3098de550a2de46142049234602dffd50596c574816e5b
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=Plasma Qt platform theme integration
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-widgets +qt6base-dbus +qt6quick +qt6quick-controls2 +qt6waylandclient +kf6-kconfig +kf6-kconfigwidgets +kf6-ki18n +kf6-kiconthemes +kf6-kio +kf6-knotifications +kf6-kstatusnotifieritem +kf6-kwindowsystem +kf6-kxmlgui +kf6-kcolorscheme +kf6-kguiaddons +kf6-kjobwidgets +kf6-kcompletion +kf6-kwidgetsaddons +kf6-kcoreaddons +kf6-kservice +breeze +qqc2-breeze-style +libwayland +libX11 +libXcursor +libxcb +xdg-desktop-portal-kde
PKG_BUILD_DEPENDS:=kf6-kconfig/host wayland wayland-protocols plasma-wayland-protocols
KF6_CMAKE_OPTIONS:=-DBUILD_QT5=OFF -DBUILD_QT6=ON -DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake"

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
