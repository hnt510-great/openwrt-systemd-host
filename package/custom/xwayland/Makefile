include $(TOPDIR)/rules.mk

PKG_NAME:=xwayland
PKG_VERSION:=24.1.14
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://xorg.freedesktop.org/archive/individual/xserver/
PKG_HASH:=4eb6b98d678299a4b96138d886345b294130695760345ef84596225a8224078a
PKG_BUILD_DEPENDS:=wayland/host wayland-protocols xorgproto xtrans xkbcomp
PKG_BUILD_PARALLEL:=1
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=COPYING

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/xwayland
  SECTION:=video
  CATEGORY:=Video
  TITLE:=Rootless X11 server for Wayland desktops
  URL:=https://wayland.freedesktop.org/xserver.html
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +libX11 +libXfont2 +libxkbfile \
	+libxcvt +libxshmfence +libwayland +pixman +libdrm +libepoxy \
	+libmesa +libglvnd +libopenssl +libbsd +xkbcomp +xkeyboard-config
endef

MESON_ARGS += \
	--wrap-mode=nofallback \
	-Dglamor=true -Dglx=true -Ddri3=true -Ddrm=true \
	-Dxvfb=false -Dxwayland_ei=false -Dlibdecor=false \
	-Dxdmcp=false -Dxdm-auth-1=false -Dsecure-rpc=false \
	-Dlisten_tcp=false -Dsystemd_notify=false -Dxselinux=false \
	-Dsha1=libcrypto -Ddocs=false -Ddevel-docs=false -Ddocs-pdf=false \
	-Dxkb_dir=/usr/share/X11/xkb -Dxkb_bin_dir=/usr/bin \
	-Dxkb_output_dir=/tmp -Dxwayland-path=/usr/bin

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/lib/pkgconfig
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/xwayland.pc $(1)/usr/lib/pkgconfig/
endef

define Package/xwayland/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/Xwayland $(1)/usr/bin/
endef

$(eval $(call BuildPackage,xwayland))
