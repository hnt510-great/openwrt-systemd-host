# Shared native KDE Frameworks 6 staging for source-built KF6 modules.
# Recipes declare their own source tarball, release, dependencies and any
# framework-specific CMake switches. Host Qt tools (moc, uic, rcc and the
# D-Bus code generators) are taken from the qt6base host build.
PKG_INSTALL:=1
# KF6 modules are consumed from the staging directory through their installed
# CMake package files, headers and pkg-config files.
CMAKE_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS+=extra-cmake-modules gettext-full/host qt6base/host qt6tools
PKG_FILE_DEPENDS+=$(INCLUDE_DIR)/kf6-package.mk
# Upstream tarballs unpack into <upstream-name>-<version>, without the kf6-
# package prefix used by the OpenWrt package names.
PKG_BUILD_DIR:=$(BUILD_DIR)/$(patsubst kf6-%,%,$(PKG_NAME))-$(PKG_VERSION)

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

# KF6 modules are shared libraries consumed by other KF6 modules and plugins.
CMAKE_OPTIONS += \
	-DBUILD_SHARED_LIBS=ON \
	-DBUILD_TESTING=OFF \
	-DBUILD_QCH=OFF \
	-DBUILD_PYTHON_BINDINGS=OFF \
	-DQT_HOST_PATH="$(STAGING_DIR_HOSTPKG)" \
	-DECM_DIR="$(STAGING_DIR)/usr/share/ECM/cmake" \
	-DKDE_INSTALL_USE_QT_SYS_PATHS=OFF \
	-DKDE_INSTALL_LIBDIR=lib \
	-DKDE_INSTALL_QTPLUGINDIR=lib/qt6/plugins \
	-DKDE_INSTALL_PLUGINDIR=lib/qt6/plugins \
	-DKDE_INSTALL_QMLDIR=lib/qt6/qml \
	$(KF6_CMAKE_OPTIONS)

# Qt6 forbids sstrip; keep the same choice for KF6 plugins and libraries.
ifneq ($(CONFIG_USE_SSTRIP),)
  STRIP:=$(TARGET_CROSS)strip $(call qstrip,$(CONFIG_STRIP_ARGS))
  RSTRIP:= \
    export CROSS="$(TARGET_CROSS)" \
		$(if $(CONFIG_KERNEL_KALLSYMS),NO_RENAME=1) \
		$(if $(CONFIG_KERNEL_PROFILING),KEEP_SYMBOLS=1); \
    NM="$(TARGET_CROSS)nm" \
    STRIP="$(STRIP)" \
    STRIP_KMOD="$(SCRIPT_DIR)/strip-kmod.sh" \
    $(SCRIPT_DIR)/rstrip.sh
endif

define Package/$(PKG_NAME)
  SECTION:=$(if $(KF6_SECTION),$(KF6_SECTION),libs)
  CATEGORY:=$(if $(KF6_CATEGORY),$(KF6_CATEGORY),Libraries)
  SUBMENU:=$(if $(KF6_SUBMENU),$(KF6_SUBMENU),KDE Frameworks 6)
  TITLE:=$(if $(KF6_PACKAGE_TITLE),$(KF6_PACKAGE_TITLE),KF6 $(KF6_TITLE))
  URL:=https://kde.org/
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD $(KF6_DEPENDS)
endef

define Package/$(PKG_NAME)/install
	[ ! -d $(PKG_INSTALL_DIR)/usr ] || $(CP) $(PKG_INSTALL_DIR)/usr $(1)/
	[ ! -d $(PKG_INSTALL_DIR)/etc ] || $(CP) $(PKG_INSTALL_DIR)/etc $(1)/
	$(RM) -r $(1)/usr/include $(1)/usr/lib/cmake $(1)/usr/lib/pkgconfig \
		$(1)/usr/share/doc $(1)/usr/share/man
	find $(1) -type f \( -name '*.a' -o -name '*.la' \) -delete
endef
