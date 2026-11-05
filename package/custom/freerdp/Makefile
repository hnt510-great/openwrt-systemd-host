include $(TOPDIR)/rules.mk

PKG_NAME:=freerdp
PKG_VERSION:=3.33.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://pub.freerdp.com/releases
PKG_HASH:=80cbcf17a7de00909f2be805c7d93764596cd712046addc18c30594137c0b879
PKG_LICENSE:=Apache-2.0
PKG_LICENSE_FILES:=LICENSE
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/cmake.mk

CMAKE_BINARY_SUBDIR:=openwrt-build

define Package/libwinpr3
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=WinPR runtime for FreeRDP 3
  DEPENDS:=+libopenssl +libpthread +librt
endef

define Package/libfreerdp3
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=FreeRDP 3 core, client and server libraries
  DEPENDS:=+libwinpr3 +libopenssl +zlib +libpthread +libopus +libsoxr +libusb-1.0
endef

define Package/winpr-hash
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=WinPR NTLM credential hashing tool
  DEPENDS:=+libwinpr3
endef

CMAKE_OPTIONS += \
	-DBUILD_SHARED_LIBS=ON -DBUILD_TESTING=OFF -DWITH_MANPAGES=OFF \
	-DWITH_CLIENT=ON -DWITH_CLIENT_COMMON=ON -DWITH_CLIENT_CHANNELS=ON \
	-DWITH_SERVER=ON -DWITH_SERVER_CHANNELS=ON -DWITH_CHANNELS=ON \
	-DWITH_SHADOW=OFF -DWITH_PROXY=OFF -DWITH_SAMPLE=OFF -DWITH_PLATFORM_SERVER=OFF \
	-DWITH_WINPR_TOOLS=ON -DWITH_X11=OFF -DWITH_WAYLAND=OFF \
	-DWITH_FFMPEG=OFF -DWITH_SWSCALE=OFF -DWITH_OPENH264=OFF -DWITH_OPUS=ON -DWITH_SOXR=ON \
	-DWITH_ALSA=OFF -DWITH_PULSE=OFF -DWITH_OSS=OFF -DWITH_SNDIO=OFF \
	-DWITH_CUPS=OFF -DWITH_PCSC=OFF -DWITH_PKCS11=OFF -DWITH_SMARTCARD_EMULATE=OFF \
	-DWITH_KRB5=OFF -DWITH_KERBEROS=OFF -DWITH_AAD=OFF -DWITH_FUSE=OFF \
	-DWITH_URIPARSER=OFF -DWITH_UNICODE_BUILTIN=ON -DWITH_JSON_DISABLED=ON -DWITH_SYSTEMD=OFF \
	-DWITH_INTERNAL_MD4=ON -DWITH_INTERNAL_MD5=ON -DWITH_INTERNAL_RC4=ON \
	-DWITH_CLANG_FORMAT=OFF -DWITH_CCACHE=OFF

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig $(1)/usr/lib/cmake
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/cmake/. $(1)/usr/lib/cmake/
endef

define Package/libwinpr3/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libwinpr3.so.* $(1)/usr/lib/
endef

define Package/libfreerdp3/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libfreerdp3.so.* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libfreerdp-server3.so.* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libfreerdp-client3.so.* $(1)/usr/lib/
endef

define Package/winpr-hash/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/winpr-hash $(1)/usr/bin/
endef

$(eval $(call BuildPackage,libwinpr3))
$(eval $(call BuildPackage,libfreerdp3))
$(eval $(call BuildPackage,winpr-hash))
