include $(TOPDIR)/rules.mk

PKG_NAME:=virglrenderer
PKG_VERSION:=1.3.0
PKG_RELEASE:=1

PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://gitlab.freedesktop.org/virgl/virglrenderer/-/archive/$(PKG_VERSION)
PKG_HASH:=065bc56e89e6f631f96101cd62eba0748e48eb888b434edc86e89d05395e76f3

PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=COPYING
PKG_CPE_ID:=cpe:/a:virglrenderer_project:virglrenderer

PKG_INSTALL:=1

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/virglrenderer
  SECTION:=libs
  CATEGORY:=Libraries
  SUBMENU:=Video
  TITLE:=VirGL virtual OpenGL renderer
  URL:=https://gitlab.freedesktop.org/virgl/virglrenderer
  DEPENDS:=+libdrm +libepoxy +libmesa +libpthread
endef

define Package/virglrenderer/description
  VirGL renderer provides a virtual OpenGL implementation for QEMU's
  VirtIO GPU devices. This build uses EGL and GBM for headless rendering.
endef

MESON_ARGS += \
	-Dplatforms=egl \
	-Dminigbm_allocation=false \
	-Dvenus=false \
	-Ddrm-renderers= \
	-Dvideo=false \
	-Dtests=false \
	-Dfuzzer=false \
	-Dvalgrind=false \
	-Dtracing=none \
	-Dunstable-apis=false

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include/virgl
	$(CP) $(PKG_INSTALL_DIR)/usr/include/virgl/*.h $(1)/usr/include/virgl/
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libvirglrenderer.so* $(1)/usr/lib/
	$(INSTALL_DIR) $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/virglrenderer.pc $(1)/usr/lib/pkgconfig/
endef

define Package/virglrenderer/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libvirglrenderer.so* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,virglrenderer))
