include $(TOPDIR)/rules.mk

PKG_NAME:=libglvnd
PKG_VERSION:=1.7.0
PKG_RELEASE:=2
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/NVIDIA/libglvnd/tar.gz/refs/tags/
PKG_SOURCE_URL_FILE:=v$(PKG_VERSION)
PKG_HASH:=073e7292788d4d3eeb45ea6c7bdcce9bfdb3b3eef8d7dbd47f2f30dce046ef98
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=README.md
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=xorgproto

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

MESON_ARGS += -Dx11=enabled -Dglx=enabled -Degl=true -Dhgl=false \
	-Dgles1=true -Dgles2=true

define Package/libglvnd
  SECTION:=libs
  CATEGORY:=Libraries
  SUBMENU:=Video
  TITLE:=Vendor-neutral EGL and OpenGL dispatch
  URL:=https://github.com/NVIDIA/libglvnd
  DEPENDS:=+libpthread +libX11 +libXext
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/lib*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
endef

define Package/libglvnd/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/lib*.so.* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,libglvnd))
