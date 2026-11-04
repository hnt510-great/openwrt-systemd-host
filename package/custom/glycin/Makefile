include $(TOPDIR)/rules.mk

PKG_NAME:=glycin
PKG_VERSION:=2.2.6
PKG_RELEASE:=1
PKG_SOURCE:=glycin-2.2.6.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/glycin/2.2/
PKG_HASH:=6a114aa1117ec2d7bd578c8cefd235d993304dedfd1a62575dc31be9a146b791
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=rust/host
GNOME_TITLE:=Sandboxed GNOME image decoders
GNOME_DEPENDS:=+librsvg +glib2-gir +gtk4 +libseccomp +fontconfig +bubblewrap +libstdcpp
GNOME_MESON_ARGS:=-Dglycin-loaders=true -Dloaders=glycin-image-rs,glycin-svg -Dlibglycin=true -Dlibglycin-gtk4=true -Dintrospection=true -Dvapi=false -Dtests=false -Dglycin-thumbnailer=true -Dlto=false

include $(INCLUDE_DIR)/gnome-package.mk
include $(INCLUDE_DIR)/gnome-rust.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
