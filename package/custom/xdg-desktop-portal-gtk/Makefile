include $(TOPDIR)/rules.mk

PKG_NAME:=xdg-desktop-portal-gtk
PKG_VERSION:=1.15.3
PKG_RELEASE:=1
PKG_SOURCE:=xdg-desktop-portal-gtk-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://github.com/flatpak/xdg-desktop-portal-gtk/releases/download/$(PKG_VERSION)
PKG_HASH:=47a3743d2419a8601e691db37e85bb5fac5ae4b26842177065cd5f22ada23b37
PKG_LICENSE:=LGPL-2.1-or-later
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/xdg-desktop-portal-gtk
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=xdg-desktop-portal-gtk for the native Flatpak desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +glib2 +libgtk3 +xdg-desktop-portal
endef

MESON_ARGS += --prefix=/usr --libdir=lib --sysconfdir=/etc --localstatedir=/var \
	-Ddefault_library=shared --wrap-mode=nodownload -Dwallpaper=disabled -Dsettings=disabled \
	-Dlockdown=disabled -Dappchooser=enabled -Dsystemd-user-unit-dir=/usr/lib/systemd/user


define Package/xdg-desktop-portal-gtk/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/lib/systemd $(1)/usr/share
	$(CP) $(PKG_INSTALL_DIR)/usr/libexec/. $(1)/usr/libexec/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/systemd/user $(1)/usr/lib/systemd/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/dbus-1 $(PKG_INSTALL_DIR)/usr/share/xdg-desktop-portal $(1)/usr/share/
endef

$(eval $(call BuildPackage,xdg-desktop-portal-gtk))
