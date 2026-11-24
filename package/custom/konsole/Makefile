include $(TOPDIR)/rules.mk

PKG_NAME:=konsole
PKG_VERSION:=26.08.3
PKG_RELEASE:=4
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/release-service/26.08.3/src/
PKG_HASH:=3189d1d048300fbe0628eab001b8ea11bfd6fe4fb6c0bbabc7c5aa0461dad430
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_TITLE:=Konsole terminal emulator
KF6_SECTION:=utils
KF6_CATEGORY:=Utilities
KF6_SUBMENU:=Terminal
KF6_PACKAGE_TITLE:=Konsole (KDE terminal emulator)
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-widgets +qt6base-printsupport \
	+qt6base-dbus +qt6base-network +qt6base-xml +qt6multimedia \
	+qt6waylandclient +qt6base-plugin-platforms-xcb +icu \
	+libX11 +libxkbcommon +kf6-breeze-icons +kf6-kbookmarks +kf6-kconfig \
	+kf6-kconfigwidgets \
	+kf6-kcoreaddons +kf6-kcrash +kf6-kdbusaddons +kf6-kglobalaccel \
	+kf6-kguiaddons +kf6-ki18n +kf6-kiconthemes +kf6-kio +kf6-knewstuff \
	+kf6-knotifications +kf6-knotifyconfig +kf6-kparts +kf6-kpty \
	+kf6-kservice +kf6-ktextwidgets +kf6-kwidgetsaddons +kf6-kwindowsystem \
	+kf6-kxmlgui
KF6_CMAKE_OPTIONS:=-DWITH_LIBSSH=OFF -DWITH_X11=ON -DUSE_DBUS=ON \
	-DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake"
PKG_BUILD_DEPENDS:=kf6-kconfig/host

# libpulse keeps its private helper library in lib/pulseaudio. The pkg-config
# file carries an rpath-link for the build host's /usr/lib, which does not
# exist in the staging tree; executable links through Qt Multimedia need the
# staged copy.
TARGET_LDFLAGS += -Wl,-rpath-link,$(STAGING_DIR)/usr/lib/pulseaudio

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
