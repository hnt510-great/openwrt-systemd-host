include $(TOPDIR)/rules.mk

PKG_NAME:=gnome-control-center
PKG_VERSION:=51.1
PKG_RELEASE:=1
PKG_SOURCE:=gnome-control-center-51.1.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gnome-control-center/51/
PKG_HASH:=1054976c2f1977f770ba134b872f547c89db7005e4422f09a96d521379c083cb
PKG_LICENSE:=GPL-2.0-or-later
PKG_BUILD_DEPENDS:=blueprint-compiler/host
GNOME_TITLE:=GNOME Settings for the netifd desktop
GNOME_DEPENDS:=+gsound +gtk4 +libadwaita +tecla +accountsservice +colord +gnome-desktop +gnome-settings-daemon +gsettings-desktop-schemas +libxml2 +libpulse-mainloop-glib +upower +libgudev +libepoxy +gcr4 +libpwquality +polkit +libibus +libgtop +libudisks2 +libsecret +libgnutls +krb5-libs +libxkbcommon
GNOME_MESON_ARGS:=-Ddisabled_panels=network,wwan,bluetooth,wacom,online-accounts,printers,color -Dtests=false -Ddocumentation=false -Dsnap=false -Dmalcontent=false -Dlocation-services=disabled -Dibus=true

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
