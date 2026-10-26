include $(TOPDIR)/rules.mk

PKG_NAME:=fcitx5
PKG_VERSION:=5.1.23
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.zst
PKG_SOURCE_URL:=https://download.fcitx-im.org/fcitx5/fcitx5/
PKG_HASH:=d287119db9dc3113bb3a2b0e78ce8670e064b744c14d3aaec69799374aadb00b
PKG_LICENSE:=LGPL-2.1-or-later
PKG_INSTALL:=1
PKG_BUILD_DEPENDS:=extra-cmake-modules nlohmannjson wayland/host wayland-protocols gettext-full/host
CMAKE_INSTALL:=1
include $(INCLUDE_DIR)/package.mk

include $(INCLUDE_DIR)/cmake.mk

define Package/fcitx5
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Fcitx5 Wayland input method framework
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libstdcpp +libuv +libdbus +libuuid +libexpat +libintl-full +libxkbcommon +xkeyboard-config +iso-codes +libwayland +libcairo +libpango +libgdk-pixbuf +glib2 +zlib
endef

CMAKE_OPTIONS += -DCMAKE_INSTALL_LIBDIR=lib -DDL_LIBRARY=$(TOOLCHAIN_DIR)/lib/libdl.a \
	-DECM_DIR=$(STAGING_DIR)/usr/share/ECM/cmake \
	-DENABLE_X11=OFF -DENABLE_WAYLAND=ON -DENABLE_TEST=OFF -DENABLE_TESTING_ADDONS=OFF \
	-DENABLE_ENCHANT=OFF -DENABLE_XDGAUTOSTART=OFF -DBUILD_SPELL_DICT=OFF \
	-DENABLE_RSVG=OFF -DUSE_SYSTEMD=OFF -DEVENT_LOOP_BACKEND=libuv \
	-DUSE_SYSTEM_PLASMA_WAYLAND_PROTOCOLS=OFF \
	-DISOCODES_ISO639_JSON=/usr/share/iso-codes/json/iso_639-3.json

define Build/InstallDev
	$(call Build/InstallDev/cmake,$(1))
	# Upstream exports absolute header paths; only staged consumers need a sysroot.
	$(SED) 's|/usr/include/Fcitx5|$(STAGING_DIR)/usr/include/Fcitx5|g' \
		$(1)/usr/lib/cmake/Fcitx5*/*Targets*.cmake \
		$(1)/usr/lib/cmake/Fcitx5Module*/Fcitx5Module*Config.cmake
endef

define Package/fcitx5/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib $(1)/usr/share
	$(CP) $(PKG_INSTALL_DIR)/usr/bin/* $(1)/usr/bin/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/fcitx5 $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/fcitx5 $(1)/usr/share/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/icons $(1)/usr/share/
endef
$(eval $(call BuildPackage,fcitx5))
