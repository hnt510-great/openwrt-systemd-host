include $(TOPDIR)/rules.mk

PKG_NAME:=kwin
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=fd5cb783f220ea4526a9afee2f72b582c3e87ef7f91b19bc5c7a6662ffe7fbdc
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=KWin Wayland compositor
KF6_DEPENDS:=+qt6base-concurrent +qt6base-core +qt65compat +qt6base-dbus +qt6quick +qt6waylandclient +qt6base-widgets +qt6svg +qt6tools +kpipewire +kf6-kauth +kf6-kcolorscheme +kf6-kconfig +kf6-kcoreaddons +kf6-kcrash +kf6-kdbusaddons +kf6-kglobalaccel +kf6-kguiaddons +kf6-ki18n +kf6-kidletime +kf6-kpackage +kf6-kservice +kf6-ksvg +kf6-kwidgetsaddons +kf6-kwindowsystem +kf6-kdeclarative +kf6-kcmutils +kf6-knewstuff +kf6-kxmlgui +kf6-krunner +kf6-kirigami +kf6-knotifications +knighttime +kwayland +libcap +plasma-activities +libplasma +kdecoration +breeze +aurorae +kglobalacceld +kscreenlocker +libmesa +libepoxy +vulkan-loader +libwayland +libxkbcommon +libxkbcommon-x11 +libcanberra +libX11 +libxcb +libxcb-cursor +libxcb-keysyms +libxcb-wm +libxcb-util +xwayland +libinput +libei +libudev +libdrm +liblcms2 +pciids +pnpids +usbids +libxcvt +libdisplay-info +pipewire +libevdev +libsystemd
PKG_BUILD_DEPENDS:=kf6-kconfig/host qt6tools wayland wayland-protocols plasma-wayland-protocols vulkan-headers libxcvt libdisplay-info libinput libei lcms2 libdrm libepoxy mesa hwdata
KF6_CMAKE_OPTIONS:=-DKWIN_BUILD_X11=ON -DCMAKE_DISABLE_FIND_PACKAGE_KF6DocTools=ON -DCMAKE_DISABLE_FIND_PACKAGE_QAccessibilityClient6=ON -DNATIVE_PREFIX="$(STAGING_DIR_HOSTPKG)" -DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake"

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
