include $(TOPDIR)/rules.mk

PKG_NAME:=plasma-workspace
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=3f984e2d960c252ee6353ef639807379c7d1bb2777fecedd047943209c52ffcb
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=Plasma Workspace
KF6_DEPENDS:=+qt6base-concurrent +qt6base-dbus +qt6location +qt6base-network +qt6positioning +qt6quick +qt6quick-widgets +qt6base-sql +qt6svg +qt6base-widgets +qt6base-printsupport +qt6waylandclient +qcoro6 +kf6-karchive +kf6-kauth +kf6-kcoreaddons +kf6-kcrash +kf6-kdbusaddons +kf6-kdeclarative +kf6-kglobalaccel +kf6-kguiaddons +kf6-kholidays +kf6-ki18n +kf6-kiconthemes +kf6-kidletime +kf6-kitemmodels +kf6-kcmutils +kf6-kded +kf6-kio +kf6-knewstuff +kf6-knotifications +kf6-kpackage +kf6-kparts +kf6-prison +kf6-krunner +kf6-kstatusnotifieritem +kf6-ksvg +kf6-ktexteditor +kf6-ktextwidgets +kf6-kwallet +kf6-kcolorscheme +kf6-kirigami +kirigami-addons +kf6-kquickcharts +kf6-kuserfeedback +libplasma +kwayland +plasma-activities +plasma-activities-stats +libksysguard +libkscreen +layer-shell-qt +kwin +kscreenlocker +knighttime +union +libcanberra +zlib +libfreetype +fontconfig +libX11 +libxcb +libxcb-cursor +libxcb-image +libxcb-util +libwayland +libudev +polkit-qt6 +icu +pipewire +libdbus +libsystemd +accountsservice +kactivitymanagerd +milou
PKG_BUILD_DEPENDS:=kf6-kconfig/host qt6shadertools wayland wayland-protocols plasma-wayland-protocols accountsservice
KF6_CMAKE_OPTIONS:=-DWITH_X11=OFF -DBUILD_xembed-sni-proxy=OFF -DBUILD_GEOTIMEZONED=OFF -DCMAKE_DISABLE_FIND_PACKAGE_KF6DocTools=ON -DCMAKE_DISABLE_FIND_PACKAGE_AppStreamQt=ON -DCMAKE_DISABLE_FIND_PACKAGE_PackageKitQt6=ON -DCMAKE_DISABLE_FIND_PACKAGE_KExiv2Qt6=ON -DCMAKE_DISABLE_FIND_PACKAGE_KF6Baloo=ON -DCMAKE_DISABLE_FIND_PACKAGE_QALCULATE=ON -DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake"

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
