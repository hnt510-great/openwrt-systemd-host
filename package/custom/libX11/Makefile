include $(TOPDIR)/rules.mk

PKG_NAME:=libX11
PKG_VERSION:=1.8.12
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/lib/
PKG_HASH:=fa026f9bb0124f4d6c808f9aef4057aad65e7b35d8ff43951cef0abe06bb9a9a

XORG_DEPENDS:=+libxcb +libpthread
PKG_BUILD_DEPENDS:=xtrans

include ../xorg-client.mk

CONFIGURE_ARGS += --enable-xthreads --enable-xlocaledir --with-locale-lib-dir=/usr/share/X11/locale

define Package/libX11/install
	$(INSTALL_DIR) $(1)/usr/lib $(1)/usr/share/X11
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so.* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/X11/locale $(1)/usr/share/X11/
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
