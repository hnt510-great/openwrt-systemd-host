include $(TOPDIR)/rules.mk

PKG_NAME:=librsvg
PKG_VERSION:=2.62.4
PKG_RELEASE:=1
PKG_SOURCE:=librsvg-2.62.4.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/librsvg/2.62/
PKG_HASH:=c982b8157a054b803493bf994d31e50105eb948dd8da6b4ab9734e8d392712a3
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=rust/host cargo-c-bin/host
GNOME_TITLE:=SVG image rendering library
GNOME_DEPENDS:=+glib2-gir +libcairo +libpango +libxml2 +libgdk-pixbuf +libstdcpp
GNOME_MESON_ARGS:=-Dintrospection=enabled -Dpixbuf=enabled -Dpixbuf-loader=enabled -Drsvg-convert=disabled -Ddocs=disabled -Dvala=disabled -Dtests=false -Davif=disabled

include $(INCLUDE_DIR)/gnome-package.mk
include $(INCLUDE_DIR)/gnome-rust.mk

MESON_ARGS += -Dtriplet=$(RUSTC_TARGET_ARCH)

$(eval $(call BuildPackage,$(PKG_NAME)))
