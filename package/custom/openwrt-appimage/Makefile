include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-appimage
PKG_VERSION:=1
PKG_RELEASE:=3
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-appimage
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Ordinary-user AppImage support for Weston
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD \
	+openwrt-desktop +@WESTON_XWAYLAND +glibc-distro-compat \
	+libfuse +fuse-utils +libfuse3 +fuse3-utils +@FUSE3_UTILS_SETUID \
	+libnss +libcups-runtime +unshare +libgtk3 +alsa-lib +at-spi2-core +fontconfig
endef

define Package/openwrt-appimage/description
  Host libraries and ordinary-user FUSE access for downloaded x86_64
  AppImages, with Weston-managed Xwayland for X11 applications.
  Applications and their embedded runtimes are not downloaded automatically.
endef

define Build/Compile
endef

define Package/openwrt-appimage/install
	$(INSTALL_DIR) $(1)/etc/hotplug.json.d $(1)/etc/udev/rules.d
	$(INSTALL_DATA) ./files/appimage-fuse.json $(1)/etc/hotplug.json.d/
	$(INSTALL_DATA) ./files/99-appimage-fuse.rules $(1)/etc/udev/rules.d/
endef

$(eval $(call BuildPackage,openwrt-appimage))
