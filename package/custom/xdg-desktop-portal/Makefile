include $(TOPDIR)/rules.mk

PKG_NAME:=xdg-desktop-portal
PKG_VERSION:=1.22.1
PKG_RELEASE:=1
PKG_SOURCE:=xdg-desktop-portal-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://github.com/flatpak/xdg-desktop-portal/releases/download/$(PKG_VERSION)
PKG_HASH:=d4879ddb3d65ff1a8f19187497e6f13dc5d267bcac404a5d501218be355753d3
PKG_LICENSE:=LGPL-2.1-or-later
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/xdg-desktop-portal
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=xdg-desktop-portal for the native Flatpak desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +glib2 +json-glib +libfuse3 +fuse3-utils +libgdk-pixbuf +libgst1pbutils +libpipewire +libsystemd +flatpak +bubblewrap
endef

MESON_ARGS += --prefix=/usr --libdir=lib --sysconfdir=/etc --localstatedir=/var \
	-Ddefault_library=shared --wrap-mode=nodownload -Dflatpak-interfaces=enabled -Dgeoclue=disabled \
	-Dgudev=disabled -Dsystemd=enabled -Ddocumentation=disabled -Dtests=disabled \
	-Dinstalled-tests=false -Dman-pages=disabled -Dsystemd-user-unit-dir=/usr/lib/systemd/user

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/share/dbus-1/interfaces $(1)/usr/share/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/share/dbus-1/interfaces/. $(1)/usr/share/dbus-1/interfaces/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/pkgconfig/*.pc $(1)/usr/share/pkgconfig/
endef
define Package/xdg-desktop-portal/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/lib/systemd $(1)/usr/share
	$(CP) $(PKG_INSTALL_DIR)/usr/libexec/. $(1)/usr/libexec/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/systemd/user $(1)/usr/lib/systemd/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/dbus-1 $(1)/usr/share/
endef

$(eval $(call BuildPackage,xdg-desktop-portal))
