include $(TOPDIR)/rules.mk

PKG_NAME:=pipewire
PKG_VERSION:=1.6.9
PKG_RELEASE:=3
PKG_BUILD_DIR:=$(BUILD_DIR)/pipewire-$(PKG_VERSION)
PKG_SOURCE:=pipewire-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/PipeWire/pipewire/tar.gz/refs/tags/$(PKG_VERSION)?
PKG_HASH:=dbc3624cf71215c26a22fc98f6f71f7b8599f5f6b415eab4a5c90ca96c170c7c
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/libpipewire
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=libpipewire for the native Flatpak desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +libpthread +librt +libdbus
endef

MESON_ARGS += --prefix=/usr --libdir=lib --sysconfdir=/etc --localstatedir=/var \
	-Ddefault_library=shared --wrap-mode=nodownload -Dauto_features=disabled -Dexamples=disabled \
	-Dtests=disabled -Dinstalled_tests=disabled -Dpipewire-jack=disabled -Dpipewire-v4l2=disabled \
	-Dspa-plugins=enabled -Dsupport=enabled -Dsession-managers=[] -Dpam-defaults-install=false \
	-Drlimits-install=false

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
endef

define Package/libpipewire/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so.* $(1)/usr/lib/
	$(INSTALL_DIR) $(1)/usr/lib/spa-0.2/support
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/spa-0.2/support/*.so $(1)/usr/lib/spa-0.2/support/
	$(INSTALL_DIR) $(1)/usr/share/pipewire $(1)/usr/lib/pipewire-0.3
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/pipewire/client.conf $(1)/usr/share/pipewire/
	for module in protocol-native client-node client-device adapter metadata session-manager; do \
		$(CP) $(PKG_INSTALL_DIR)/usr/lib/pipewire-0.3/libpipewire-module-$$$$module.so \
			$(1)/usr/lib/pipewire-0.3/; \
	done
endef

$(eval $(call BuildPackage,libpipewire))
