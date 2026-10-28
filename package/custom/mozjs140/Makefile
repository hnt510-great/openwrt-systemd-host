include $(TOPDIR)/rules.mk

PKG_NAME:=mozjs140
PKG_VERSION:=140.15.0
PKG_RELEASE:=1
PKG_SOURCE:=firefox-$(PKG_VERSION)esr.source.tar.xz
PKG_SOURCE_URL:=https://archive.mozilla.org/pub/firefox/releases/$(PKG_VERSION)esr/source/
PKG_HASH:=358bb03c550f95172f1e31694e4287da3411560df91e931cb25210efdf90e524
PKG_BUILD_DIR:=$(BUILD_DIR)/firefox-$(PKG_VERSION)
PKG_LICENSE:=MPL-2.0
PKG_LICENSE_FILES:=LICENSE
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=python3/host rust/host cbindgen-bin/host
PKG_UNPACK:=xzcat $(DL_DIR)/$(PKG_SOURCE) | $(TAR) -C $(BUILD_DIR) -xf -

include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/rust/rust-values.mk

define Package/mozjs140
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=SpiderMonkey 140 JavaScript engine for GJS
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libstdcpp +libatomic +zlib +icu
endef

MOZJS_OBJDIR:=$(PKG_BUILD_DIR)/openwrt-build
MOZJS_PYTHONPATH:=$(PKG_BUILD_DIR)/build:$(PKG_BUILD_DIR)/third_party/python/PyYAML/lib3:$(PKG_BUILD_DIR)/testing/mozbase/mozfile:$(PKG_BUILD_DIR)/python/mozboot:$(PKG_BUILD_DIR)/third_party/python/distro:$(PKG_BUILD_DIR)/testing/mozbase/mozinfo:$(PKG_BUILD_DIR)/config:$(PKG_BUILD_DIR)/testing/mozbase/manifestparser:$(PKG_BUILD_DIR)/third_party/python/pytoml:$(PKG_BUILD_DIR)/testing/mozbase/mozprocess:$(PKG_BUILD_DIR)/third_party/python/six:$(PKG_BUILD_DIR)/python/mozbuild:$(PKG_BUILD_DIR)/python/mozbuild/mozbuild:$(PKG_BUILD_DIR)/python/mach:$(PKG_BUILD_DIR)/third_party/python/jsmin:$(PKG_BUILD_DIR)/python/mozversioncontrol
MOZJS_VARS=CC="$(TARGET_CC)" CXX="$(TARGET_CXX)" AR="$(TARGET_AR)" \
	HOST_CC="$(HOSTCC_NOCACHE)" HOST_CXX="$(HOSTCXX_NOCACHE)" \
	CFLAGS="$(TARGET_CFLAGS) $(TARGET_CPPFLAGS)" CXXFLAGS="$(TARGET_CFLAGS) $(TARGET_CPPFLAGS)" \
	LDFLAGS="$(TARGET_LDFLAGS)" PYTHONPATH="$(MOZJS_PYTHONPATH)" \
	MOZBUILD_STATE_PATH="$(PKG_BUILD_DIR)/.mozbuild" \
	MOZ_NOSPAM=1 CARGO_HOME="$(DL_DIR)/cargo" CARGO_NET_OFFLINE=true \
	CBINDGEN="$(STAGING_DIR_HOSTPKG)/bin/cbindgen" \
	PKG_CONFIG="$(PKG_CONFIG)" PKG_CONFIG_SYSROOT_DIR="$(STAGING_DIR)" \
	PKG_CONFIG_LIBDIR="$(STAGING_DIR)/usr/lib/pkgconfig:$(STAGING_DIR)/usr/share/pkgconfig"

define Build/Configure
	$(INSTALL_DIR) $(MOZJS_OBJDIR)
	(cd $(MOZJS_OBJDIR); $(MOZJS_VARS) $(STAGING_DIR_HOSTPKG)/bin/python3 \
		$(PKG_BUILD_DIR)/configure.py --enable-project=js \
		--target=$(RUSTC_TARGET_ARCH) --host=$(GNU_HOST_NAME) \
		--prefix=/usr --libdir=/usr/lib --disable-jemalloc --disable-strip \
		--disable-debug-symbols --with-system-zlib --with-system-icu)
endef

define Build/Compile
	+$(MOZJS_VARS) $(MAKE) $(PKG_JOBS) -C $(MOZJS_OBJDIR)
endef

define Build/Install
	+$(MOZJS_VARS) $(MAKE) -C $(MOZJS_OBJDIR) DESTDIR=$(PKG_INSTALL_DIR) install
	$(SED) 's|^Cflags: |Cflags: -DXP_UNIX |' $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/mozjs-140.pc
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libmozjs-140.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
	$(SED) 's|^libdir=.*|libdir=$$$${prefix}/lib|;s|^includedir=.*|includedir=$$$${prefix}/include|' $(1)/usr/lib/pkgconfig/mozjs-140.pc
endef

define Package/mozjs140/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libmozjs-140.so* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,mozjs140))
