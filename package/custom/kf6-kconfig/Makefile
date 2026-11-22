include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kconfig
PKG_VERSION:=6.20.0
PKG_RELEASE:=1
PKG_SOURCE:=kconfig-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=daecf4989af9958144139e4918c22cd05b5a96527c51d737eae7c57718167d15
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Config
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-xml +qt6base-dbus
KF6_CMAKE_OPTIONS:=-DKCONFIG_USE_QML=OFF -DUSE_DBUS=ON

# Konsole uses kconfig_add_kcfg_files() at build time.  Build a host copy of
# kconfig_compiler and point consumers at it through KF6_HOST_TOOLING.
HOST_BUILD_DEPENDS:=qt6base/host qt6tools/host extra-cmake-modules/host
HOST_BUILD_DIR:=$(BUILD_DIR_HOST)/kconfig-$(PKG_VERSION)
HOST_BUILD_PARALLEL:=1
CMAKE_HOST_OPTIONS += \
	-DECM_DIR="$(STAGING_DIR_HOSTPKG)/share/ECM/cmake" \
	-DQT_HOST_PATH="$(STAGING_DIR_HOSTPKG)" \
	-DKDE_INSTALL_USE_QT_SYS_PATHS=OFF \
	-DKDE_INSTALL_LIBDIR=lib \
	-DKCONFIG_USE_GUI=OFF \
	-DKCONFIG_USE_QML=OFF \
	-DUSE_DBUS=OFF \
	-DBUILD_QCH=OFF \
	-DBUILD_PYTHON_BINDINGS=OFF \
	-DCMAKE_SKIP_RPATH=FALSE \
	-DCMAKE_INSTALL_RPATH="$(STAGING_DIR_HOSTPKG)/lib"

# host-build.mk must come before cmake.mk (through kf6-package.mk) so that
# the CMake host configure/build rules provide the Host/ defaults.
include $(INCLUDE_DIR)/host-build.mk
include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
$(eval $(call HostBuild))
