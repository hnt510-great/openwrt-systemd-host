include $(TOPDIR)/rules.mk

PKG_NAME:=neatvnc
PKG_VERSION:=1.0.4
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/any1/neatvnc/tar.gz/v$(PKG_VERSION)?
PKG_HASH:=c40d74bb788a60519e6c926f04515502de7859abcfd74f2a18f97bd02f4dc231
PKG_LICENSE:=ISC
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_DEPENDS:=libdrm

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/libneatvnc
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=VNC server library with TLS support
  URL:=https://github.com/any1/neatvnc
  DEPENDS:=+libaml +pixman +zlib +libgnutls +libnettle +libgmp
endef

MESON_ARGS += \
	--wrap-mode=nofallback \
	-Dtls=enabled \
	-Dnettle=enabled \
	-Djpeg=disabled \
	-Dgbm=disabled \
	-Dh264=disabled \
	-Dexamples=false \
	-Dtests=false \
	-Dbenchmarks=false

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/* $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libneatvnc.so* $(1)/usr/lib/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/neatvnc.pc $(1)/usr/lib/pkgconfig/
endef

define Package/libneatvnc/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libneatvnc.so* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,libneatvnc))
