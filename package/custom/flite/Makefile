include $(TOPDIR)/rules.mk

PKG_NAME:=flite
PKG_VERSION:=2.2
PKG_RELEASE:=1
PKG_SOURCE:=flite-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://github.com/festvox/flite/archive/refs/tags/v$(PKG_VERSION).tar.gz
PKG_HASH:=ab1555fe5adc3f99f1d4a1a0eb1596d329fd6d74f1464a0097c81f53c0cf9e5c
PKG_LICENSE:=BSD-2-Clause
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk

# The Qt TextToSpeech flite plugin drives the synthesizer through its own
# audio callback, so Flite's own audio backend (ALSA) is not built.
CONFIGURE_ARGS += \
	--enable-shared \
	--with-audio=none \
	--disable-sockets

define Package/libflite
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=CMU Flite speech synthesis library
  URL:=http://www.festvox.org/flite/
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libstdcpp +alsa-lib
endef

define Package/libflite/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	[ ! -d $(PKG_INSTALL_DIR)/usr/share/flite ] || \
		$(CP) $(PKG_INSTALL_DIR)/usr/share/flite $(1)/usr/share/
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/include/flite $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
endef

$(eval $(call BuildPackage,libflite))
