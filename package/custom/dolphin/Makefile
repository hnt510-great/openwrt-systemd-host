include $(TOPDIR)/rules.mk

PKG_NAME:=dolphin
PKG_VERSION:=26.08.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/release-service/26.08.3/src/
PKG_HASH:=8d73851ba561f81b9aa27bba53157a59d9eeaa548fd82f0c9c2167b5a7c4a65d
PKG_LICENSE:=GPL-2.0-or-later

KF6_SECTION:=utils
KF6_CATEGORY:=Utilities
KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=Dolphin (KDE file manager)
KF6_DEPENDS:=+qt6base-core +qt6base-concurrent +qt6base-widgets +qt6base-gui +qt6base-dbus \
	+qt6multimedia +qt6multimedia-widgets +qt6waylandclient \
	+kf6-kcmutils +kf6-knewstuff +kf6-kcoreaddons +kf6-ki18n +kf6-kdbusaddons \
	+kf6-kbookmarks +kf6-kconfig +kf6-kio +kf6-kparts +kf6-solid +kf6-kiconthemes \
	+kf6-kcompletion +kf6-ktextwidgets +kf6-knotifications +kf6-kcrash \
	+kf6-kwindowsystem +kf6-kwidgetsaddons +kf6-kcodecs +kf6-kguiaddons +kf6-kcolorscheme \
	+kf6-kfilemetadata +kf6-kuserfeedback
KF6_CMAKE_OPTIONS:=-DCMAKE_DISABLE_FIND_PACKAGE_KF6DocTools=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_PackageKitQt6=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_KF6Baloo=ON \
	-DCMAKE_DISABLE_FIND_PACKAGE_KF6BalooWidgets=ON \
	-DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake"
PKG_BUILD_DEPENDS:=kf6-kconfig/host
TARGET_LDFLAGS += -Wl,-rpath-link,$(STAGING_DIR)/usr/lib/pulseaudio

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
