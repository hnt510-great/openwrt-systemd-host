include $(TOPDIR)/rules.mk

PKG_NAME:=plasma-desktop
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=aa050cfb1005d6f806dc347bb11bc583d5360dd11d51b4501f6328aa7b26d370
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=Plasma Desktop
KF6_DEPENDS:=+qt6quick +qt6quick-widgets +qt6base-dbus +qt6base-widgets +qt6svg +qt6base-concurrent +qt65compat +qt6base-sql +qt6waylandclient +kf6-kauth +kf6-kcrash +kf6-kconfig +kf6-ki18n +kf6-kcmutils +kf6-knewstuff +kf6-kio +kf6-knotifications +kf6-knotifyconfig +kf6-attica +kf6-krunner +kf6-kglobalaccel +kf6-kcoreaddons +kf6-kguiaddons +kf6-kdbusaddons +kf6-kwidgetsaddons +kf6-kcodecs +kf6-sonnet +kf6-kpackage +kf6-kiconthemes +kf6-kxmlgui +kf6-ksvg +kf6-kirigami +kirigami-addons +kf6-qqc2-desktop-style +kf6-kitemmodels +kf6-kded +plasma5support +libplasma +plasma-activities +plasma-activities-stats +polkit-qt6 +libcanberra +libwayland +plasma-workspace +kwin +kscreenlocker +libksysguard +libX11 +libudev +libxcb +glib2 +libibus +libwacom +libxkbcommon +libxkbfile
PKG_BUILD_DEPENDS:=kf6-kconfig/host qt6shadertools wayland wayland-protocols libwacom
KF6_CMAKE_OPTIONS:=-DBUILD_DOC=OFF -DCMAKE_DISABLE_FIND_PACKAGE_KF6DocTools=ON -DCMAKE_DISABLE_FIND_PACKAGE_AccountsQt6=ON -DCMAKE_DISABLE_FIND_PACKAGE_KAccounts6=ON -DCMAKE_DISABLE_FIND_PACKAGE_KF6Baloo=ON -DCMAKE_DISABLE_FIND_PACKAGE_PackageKitQt6=ON -DCMAKE_DISABLE_FIND_PACKAGE_SDL2=ON -DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake"

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
