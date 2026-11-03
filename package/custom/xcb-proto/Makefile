include $(TOPDIR)/rules.mk

PKG_NAME:=xcb-proto
PKG_VERSION:=1.17.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xcb.freedesktop.org/dist/
PKG_HASH:=2c1bacd2110f4799f74de6ebb714b94cf6f80fb112316b1219480fd22562148c

PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_DEPENDS:=util-macros/host python3/host
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/host-build.mk

define Package/$(PKG_NAME)
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=$(PKG_NAME) X.Org build headers
  BUILDONLY:=1
endef

CONFIGURE_ARGS += --disable-specs --disable-docs --without-xmlto --without-fop --without-xsltproc

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig $(1)/usr/share
	[ ! -d $(PKG_INSTALL_DIR)/usr/include ] || $(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	[ ! -d $(PKG_INSTALL_DIR)/usr/share/pkgconfig ] || $(CP) $(PKG_INSTALL_DIR)/usr/share/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
	[ ! -d $(PKG_INSTALL_DIR)/usr/lib/pkgconfig ] || $(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
endef

HOST_BUILD_DEPENDS:=python3/host
HOST_CONFIGURE_VARS += PYTHON="$(STAGING_DIR_HOSTPKG)/bin/python3"
HOST_CONFIGURE_ARGS += pythondir="$(STAGING_DIR_HOSTPKG)/lib/xcb-proto"
CONFIGURE_VARS += PYTHON="$(STAGING_DIR_HOSTPKG)/bin/python3"

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/share/xcb $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/share/xcb/*.xml $(1)/usr/share/xcb/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/pkgconfig/xcb-proto.pc $(1)/usr/lib/pkgconfig/
endef

$(eval $(call HostBuild))

$(eval $(call BuildPackage,$(PKG_NAME)))
