include $(TOPDIR)/rules.mk

PKG_NAME:=sunshine
PKG_VERSION:=2026.914.233613
PKG_RELEASE:=5
PKG_SOURCE:=sunshine-source-63d35f702ee9.tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/LizardByte/Sunshine/tar.gz/63d35f702ee9e362e43263742981836ec0710384?
PKG_HASH:=2564df7ee9c1ac1d617e30b406ec0ed7d358cbba485cfb013956bdab528dae5f
PKG_BUILD_DIR:=$(BUILD_DIR)/sunshine-$(PKG_VERSION)
PKG_UNPACK:=mkdir -p $(PKG_BUILD_DIR); $(TAR) -xf $(DL_DIR)/$(PKG_SOURCE) -C $(PKG_BUILD_DIR) --strip-components=1
PKG_LICENSE:=GPL-3.0-only
PKG_LICENSE_FILES:=LICENSE
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=node/host python-jinja2/host nlohmannjson wayland/host wayland-protocols

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk
include ./sources.mk

define Package/sunshine
  SECTION:=multimedia
  CATEGORY:=Multimedia
  TITLE:=Sunshine Moonlight desktop streaming host
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +openwrt-desktop-audio \
	+libstdcpp +libopenssl +libcurl +libminiupnpc +libopus +libpulse +libffmpeg \
	+libdrm +libmesa +libva +libevdev +libcap +libcap-bin +glib2-gio \
	+boost-filesystem +boost-log +boost-program_options +boost-locale +libpipewire +libwayland \
	+kmod-input-uinput +acl +shadow-groupadd
endef

define Package/sunshine/conffiles
/etc/desktop/sunshine-users
endef

CMAKE_OPTIONS += -DBUILD_DOCS=OFF -DBUILD_TESTS=OFF -DBUILD_EXAMPLES=OFF \
	-DBOOST_USE_STATIC=OFF -DSUNSHINE_ENABLE_TRAY=OFF -DSUNSHINE_ENABLE_CUDA=OFF \
	-DSUNSHINE_ENABLE_DRM=ON -DSUNSHINE_ENABLE_VAAPI=ON -DSUNSHINE_ENABLE_VULKAN=OFF \
	-DSUNSHINE_ENABLE_WAYLAND=ON -DSUNSHINE_ENABLE_X11=OFF \
	-DSUNSHINE_ENABLE_WESTON=ON -DSUNSHINE_SYSTEM_WAYLAND_PROTOCOLS=ON \
	-DSUNSHINE_ENABLE_KWIN=OFF -DSUNSHINE_ENABLE_PORTAL=OFF \
	-DLIBVIRTUALHID_ENABLE_XTEST=OFF -DLIBVIRTUALHID_BUILD_TOOLS=OFF \
	-DSUNSHINE_ASSETS_DIR=/usr/share/sunshine -DFFMPEG_CBS_ARCHIVE=$(PKG_BUILD_DIR)/libcbs.a \
	-DGLAD_SKIP_PIP_INSTALL=ON -DNPM=$(STAGING_DIR_HOSTPKG)/bin/npm -DPython_EXECUTABLE=$(STAGING_DIR_HOSTPKG)/bin/python3
CMAKE_BINARY_SUBDIR:=openwrt-build
CMAKE_SOURCE_SUBDIR:=.

# npm ci uses the release lockfile and verifies every dependency's integrity.
CMAKE_OPTIONS += -DCMAKE_EXE_LINKER_FLAGS="$(TARGET_LDFLAGS) -Wl,--exclude-libs,ALL -Wl,-rpath-link,$(STAGING_DIR)/usr/lib -Wl,-rpath-link,$(STAGING_DIR)/usr/lib/pulseaudio"
export BUILD_VERSION:=$(PKG_VERSION)
export BRANCH:=openwrt
export npm_config_cache:=$(DL_DIR)/sunshine-npm-cache
export npm_config_audit:=false
export npm_config_fund:=false

# Submodules are separately hashed downloads, not live git checkouts.
define Build/Prepare
	$(call Build/Prepare/Default)
	$(CP) ./files/westongrab.cpp $(PKG_BUILD_DIR)/src/platform/linux/
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/wlr-protocols
	$(TAR) -xf $(DL_DIR)/sunshine-wlr-protocols-bf4fc79abc35.tar.gz -C $(PKG_BUILD_DIR)/third-party/wlr-protocols --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/build-deps
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-build-deps-a1fe2841cbc0.tar.gz -C $(PKG_BUILD_DIR)/third-party/build-deps --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/glad
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-glad-73db193f853e.tar.gz -C $(PKG_BUILD_DIR)/third-party/glad --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libdisplaydevice
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libdisplaydevice-6e9722f89103.tar.gz -C $(PKG_BUILD_DIR)/third-party/libdisplaydevice --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libdisplaydevice/third-party/doxyconfig
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libdisplaydevice-third-party-doxyconfig-e552f7c9f00c.tar.gz -C $(PKG_BUILD_DIR)/third-party/libdisplaydevice/third-party/doxyconfig --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libdisplaydevice/third-party/doxyconfig/doxygen-awesome-css
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libdisplaydevice-third-party-doxyconfig-doxygen-awesome-css-d52eafe3e930.tar.gz -C $(PKG_BUILD_DIR)/third-party/libdisplaydevice/third-party/doxyconfig/doxygen-awesome-css --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libdisplaydevice/third-party/lizardbyte-common
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libdisplaydevice-third-party-lizardbyte-common-06cd442b808f.tar.gz -C $(PKG_BUILD_DIR)/third-party/libdisplaydevice/third-party/lizardbyte-common --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libdisplaydevice/third-party/lizardbyte-common/third-party/doxyconfig
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libdisplaydevice-third-party-lizardbyte-common-third-party-doxyconfig-e552f7c9f00c.tar.gz -C $(PKG_BUILD_DIR)/third-party/libdisplaydevice/third-party/lizardbyte-common/third-party/doxyconfig --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libdisplaydevice/third-party/lizardbyte-common/third-party/doxyconfig/doxygen-awesome-css
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libdisplaydevice-third-party-lizardbyte-common-third-party-doxyconfig-doxygen-awesome-css-d52eafe3e930.tar.gz -C $(PKG_BUILD_DIR)/third-party/libdisplaydevice/third-party/lizardbyte-common/third-party/doxyconfig/doxygen-awesome-css --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libdisplaydevice/third-party/lizardbyte-common/third-party/googletest
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libdisplaydevice-third-party-lizardbyte-common-third-party-googletest-52eb8108c5bd.tar.gz -C $(PKG_BUILD_DIR)/third-party/libdisplaydevice/third-party/lizardbyte-common/third-party/googletest --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libvirtualhid
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libvirtualhid-53e1a949fc07.tar.gz -C $(PKG_BUILD_DIR)/third-party/libvirtualhid --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libvirtualhid/third-party/doxyconfig
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libvirtualhid-third-party-doxyconfig-419127bad87f.tar.gz -C $(PKG_BUILD_DIR)/third-party/libvirtualhid/third-party/doxyconfig --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libvirtualhid/third-party/doxyconfig/doxygen-awesome-css
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libvirtualhid-third-party-doxyconfig-doxygen-awesome-css-46483f1e5a70.tar.gz -C $(PKG_BUILD_DIR)/third-party/libvirtualhid/third-party/doxyconfig/doxygen-awesome-css --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libvirtualhid/third-party/lizardbyte-common
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libvirtualhid-third-party-lizardbyte-common-f9d91e1d29b7.tar.gz -C $(PKG_BUILD_DIR)/third-party/libvirtualhid/third-party/lizardbyte-common --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libvirtualhid/third-party/lizardbyte-common/third-party/doxyconfig
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libvirtualhid-third-party-lizardbyte-common-third-party-doxyconfig-b87f7e4e1dcd.tar.gz -C $(PKG_BUILD_DIR)/third-party/libvirtualhid/third-party/lizardbyte-common/third-party/doxyconfig --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libvirtualhid/third-party/lizardbyte-common/third-party/doxyconfig/doxygen-awesome-css
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libvirtualhid-third-party-lizardbyte-common-third-party-doxyconfig-doxygen-awesome-css-24c4f966e375.tar.gz -C $(PKG_BUILD_DIR)/third-party/libvirtualhid/third-party/lizardbyte-common/third-party/doxyconfig/doxygen-awesome-css --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/libvirtualhid/third-party/lizardbyte-common/third-party/googletest
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-libvirtualhid-third-party-lizardbyte-common-third-party-googletest-f8d7d77c0693.tar.gz -C $(PKG_BUILD_DIR)/third-party/libvirtualhid/third-party/lizardbyte-common/third-party/googletest --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/lizardbyte-common
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-lizardbyte-common-f9d91e1d29b7.tar.gz -C $(PKG_BUILD_DIR)/third-party/lizardbyte-common --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/lizardbyte-common/third-party/doxyconfig
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-lizardbyte-common-third-party-doxyconfig-b87f7e4e1dcd.tar.gz -C $(PKG_BUILD_DIR)/third-party/lizardbyte-common/third-party/doxyconfig --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/lizardbyte-common/third-party/doxyconfig/doxygen-awesome-css
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-lizardbyte-common-third-party-doxyconfig-doxygen-awesome-css-24c4f966e375.tar.gz -C $(PKG_BUILD_DIR)/third-party/lizardbyte-common/third-party/doxyconfig/doxygen-awesome-css --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/lizardbyte-common/third-party/googletest
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-lizardbyte-common-third-party-googletest-f8d7d77c0693.tar.gz -C $(PKG_BUILD_DIR)/third-party/lizardbyte-common/third-party/googletest --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/moonlight-common-c
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-moonlight-common-c-62e066388f1a.tar.gz -C $(PKG_BUILD_DIR)/third-party/moonlight-common-c --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/moonlight-common-c/enet
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-moonlight-common-c-enet-aca87840b57f.tar.gz -C $(PKG_BUILD_DIR)/third-party/moonlight-common-c/enet --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/moonlight-common-c/nanors
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-moonlight-common-c-nanors-b1e3c22ca0cd.tar.gz -C $(PKG_BUILD_DIR)/third-party/moonlight-common-c/nanors --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/Simple-Web-Server
	$(TAR) -xf $(DL_DIR)/sunshine-third-party-Simple-Web-Server-546895a93a29.tar.gz -C $(PKG_BUILD_DIR)/third-party/Simple-Web-Server --strip-components=1
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/third-party/nv-codec-headers
	$(TAR) -xf $(DL_DIR)/sunshine-nv-codec-headers-n13.1.15.0.tar.gz -C $(PKG_BUILD_DIR)/third-party/nv-codec-headers --strip-components=1
endef

define Build/Configure
	# gcc-ranlib indexes slim LTO objects using the matching target compiler plugin.
	$(CP) $(STAGING_DIR)/usr/lib/libavcodec.a $(PKG_BUILD_DIR)/libcbs.a
	$(TARGET_CROSS)gcc-ranlib $(PKG_BUILD_DIR)/libcbs.a
	$(call Build/Configure/Default)
endef

define Package/sunshine/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] || /usr/libexec/sunshine-permissions
endef

define Package/sunshine/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/sbin $(1)/usr/libexec $(1)/usr/share
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/sunshine $(1)/usr/bin/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/sunshine $(1)/usr/share/
	$(INSTALL_BIN) ./files/sunshine-setup $(1)/usr/sbin/
	$(INSTALL_BIN) ./files/sunshine-permissions $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/sunshine-session $(1)/usr/libexec/
	$(INSTALL_DIR) $(1)/usr/lib/systemd/user $(1)/etc/init.d $(1)/etc/hotplug.d/misc $(1)/etc/hotplug.json.d $(1)/lib/upgrade/keep.d
	$(INSTALL_DATA) ./files/sunshine.service $(1)/usr/lib/systemd/user/
	$(INSTALL_BIN) ./files/sunshine-permissions.init $(1)/etc/init.d/sunshine-permissions
	$(INSTALL_BIN) ./files/sunshine.hotplug $(1)/etc/hotplug.d/misc/95-sunshine
	$(INSTALL_DATA) ./files/sunshine-uinput.json $(1)/etc/hotplug.json.d/
	$(INSTALL_DATA) ./files/sunshine.keep $(1)/lib/upgrade/keep.d/sunshine
endef

$(eval $(call BuildPackage,sunshine))
