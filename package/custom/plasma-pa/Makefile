include $(TOPDIR)/rules.mk

PKG_NAME:=plasma-pa
PKG_VERSION:=6.8.3
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/plasma/6.8.3/
PKG_HASH:=25ec7e4f2d8104adb4583a30b5d516c699109bc2631b100e549ab1ea5b2607ff
PKG_LICENSE:=GPL-2.0-or-later LGPL-2.1-or-later

KF6_SUBMENU:=KDE Plasma 6
KF6_PACKAGE_TITLE:=Plasma Audio Volume Control
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-dbus +qt6quick +qt6base-widgets +kf6-kconfig +kf6-kcoreaddons +kf6-kdeclarative +kf6-kglobalaccel +kf6-kstatusnotifieritem +kf6-ki18n +kf6-kcmutils +kf6-ksvg +kf6-kdbusaddons +kf6-kirigami +kirigami-addons +kf6-kitemmodels +libplasma +libcanberra +pulseaudio-qt +libpulse +libpulse-mainloop-glib +glib2
PKG_BUILD_DEPENDS:=kf6-kconfig/host pulseaudio
KF6_CMAKE_OPTIONS:=-DBUILD_DOC=OFF -DCMAKE_DISABLE_FIND_PACKAGE_KF6DocTools=ON -DKF6_HOST_TOOLING="$(STAGING_DIR_HOSTPKG)/lib/cmake;$(STAGING_DIR)/usr/lib/cmake"
TARGET_LDFLAGS += -Wl,-rpath-link,$(STAGING_DIR)/usr/lib/pulseaudio

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
