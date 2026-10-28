include $(TOPDIR)/rules.mk

PKG_NAME:=nv-codec-headers
PKG_VERSION:=13.1.15.0
PKG_RELEASE:=1
PKG_SOURCE:=sunshine-nv-codec-headers-n$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/FFmpeg/nv-codec-headers/tar.gz/n$(PKG_VERSION)?
PKG_HASH:=2255bc74d038b95aa4be30f5f66322c2176acbdb90ada1851db6993536fbeaf7
PKG_BUILD_DIR:=$(BUILD_DIR)/nv-codec-headers-n$(PKG_VERSION)
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=include/ffnvcodec/dynlink_loader.h
PKG_INSTALL:=1

include $(INCLUDE_DIR)/package.mk

define Package/nv-codec-headers
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=FFmpeg NVIDIA codec interface headers
  BUILDONLY:=1
endef

MAKE_FLAGS += PREFIX=/usr

define Build/Configure
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/ffnvcodec.pc $(1)/usr/lib/pkgconfig/
endef

$(eval $(call BuildPackage,nv-codec-headers))
