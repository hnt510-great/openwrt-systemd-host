include $(TOPDIR)/rules.mk

PKG_NAME:=igt-gpu-tools
PKG_VERSION:=2.6
PKG_RELEASE:=1

PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://www.x.org/releases/individual/app
PKG_HASH:=5d5190debfec0ee1728430897f243d0afa271856c2cb5834a23b23f08be8d06e

PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=COPYING
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=kmod elfutils cairo pixman

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/intel-gpu-tools
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Intel GPU usage monitor (intel_gpu_top)
  URL:=https://gitlab.freedesktop.org/drm/igt-gpu-tools
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @KERNEL_PERF_EVENTS +libdrm +libpciaccess +libpci +libudev +glib2
endef

define Package/intel-gpu-tools/description
  Display live Intel GPU engine utilization, frequency, power and per-process
  usage with intel_gpu_top. This package contains only the monitoring tool,
  without the upstream driver test suite. Run as root to read PMU counters.
endef

MESON_ARGS += \
	-Doverlay=disabled \
	-Dchamelium=disabled \
	-Dvalgrind=disabled \
	-Dman=disabled \
	-Dtestplan=disabled \
	-Dsphinx=disabled \
	-Ddocs=disabled \
	-Dtests=disabled \
	-Dxe_driver=disabled \
	-Dvmtb=disabled \
	-Dlibdrm_drivers=[] \
	-Dlibunwind=disabled \
	-Drunner=disabled \
	-Doping=disabled \
	-Duse_rpath=false \
	-Dversion_hash=$(PKG_VERSION) \
	-Dsrcdir=/usr/src/igt-gpu-tools-$(PKG_VERSION)

# intel_gpu_top uses upstream static helper libraries, not libigt.so.
define Build/Compile
	$(call Build/Compile/Meson,tools/intel_gpu_top)
endef

define Build/Install
endef

define Package/intel-gpu-tools/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/share/licenses/intel-gpu-tools
	$(INSTALL_BIN) $(MESON_BUILD_DIR)/tools/intel_gpu_top $(1)/usr/bin/
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/COPYING $(1)/usr/share/licenses/intel-gpu-tools/
endef

$(eval $(call BuildPackage,intel-gpu-tools))
