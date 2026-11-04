include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-desktop
PKG_RELEASE:=26
PKG_CONFIG_DEPENDS:=CONFIG_OPENWRT_SYSTEMD
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-desktop
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Shared GNOME desktop with LAN RDP and Sunshine
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +input-support +video-support +accel-support +systemd-udev +kmod +glibc-locale-utf8 +libpam \
	+gnome-shell +gnome-session +gnome-settings-daemon +gnome-control-center \
	+nautilus +gnome-terminal +gnome-tweaks +gnome-remote-desktop +gnome-keyring \
	+xdg-desktop-portal-gnome +python3-gobject +glib2-utils +xwayland \
	+kmod-input-evdev +dejavu-fonts-ttf-DejaVuSans +noto-sans-symbols2 \
	+dejavu-fonts-ttf-DejaVuSansMono +openssl-util \
	+shadow-usermod +shadow-useradd +shadow-passwd +tar
endef

define Package/openwrt-desktop/description
  An ordinary-user GNOME session sharing its local display over RDP and
  Sunshine. Run desktop-setup after creating a user and setting its password.
endef

define Package/openwrt-desktop/conffiles
/etc/config/desktop
/etc/pam.d/openwrt-desktop
endef

define Build/Compile
endef

define Package/openwrt-desktop/install
	$(INSTALL_DIR) $(1)/etc/config $(1)/etc/init.d $(1)/etc/pam.d
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/usr/libexec $(1)/lib/upgrade/keep.d
	$(INSTALL_DATA) ./files/desktop.config $(1)/etc/config/desktop
	$(INSTALL_BIN) ./files/desktop.init $(1)/etc/init.d/desktop
	$(INSTALL_DATA) ./files/openwrt-desktop.pam $(1)/etc/pam.d/openwrt-desktop
	$(INSTALL_BIN) ./files/desktop-setup $(1)/usr/sbin/desktop-setup
	$(INSTALL_BIN) ./files/desktop-rdp-setup $(1)/usr/sbin/desktop-rdp-setup
	$(INSTALL_BIN) ./files/desktop-keyring-unlock ./files/desktop-keyring-control-unlock ./files/desktop-user-setup ./files/desktop-user-stop $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/desktop-rdp-configure ./files/desktop-gnome-remotes ./files/desktop-gnome-settings $(1)/usr/libexec/
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system $(1)/usr/lib/systemd/user/gnome-remote-desktop.service.d
	$(INSTALL_DATA) ./files/openwrt-desktop-coldplug.service $(1)/usr/lib/systemd/system/
	$(INSTALL_BIN) ./files/desktop-gpu-coldplug $(1)/usr/libexec/
	$(INSTALL_DATA) ./files/openwrt-gnome-remotes.service $(1)/usr/lib/systemd/user/
	$(INSTALL_DATA) ./files/gnome-rdp-openwrt.conf $(1)/usr/lib/systemd/user/gnome-remote-desktop.service.d/openwrt.conf
	$(INSTALL_DIR) $(1)/usr/share/glib-2.0/schemas
	$(INSTALL_DATA) ./files/90-openwrt-desktop.gschema.override $(1)/usr/share/glib-2.0/schemas/
	$(INSTALL_BIN) ./files/desktop-session $(1)/usr/libexec/desktop-session
	$(INSTALL_DATA) ./files/desktop-common.sh $(1)/usr/libexec/desktop-common.sh
	$(INSTALL_DATA) ./files/desktop.keep $(1)/lib/upgrade/keep.d/desktop
	$(INSTALL_DIR) $(1)/etc/hotplug.d/drm
	$(INSTALL_BIN) ./files/desktop.hotplug $(1)/etc/hotplug.d/drm/95-desktop
endef

$(eval $(call BuildPackage,openwrt-desktop))
