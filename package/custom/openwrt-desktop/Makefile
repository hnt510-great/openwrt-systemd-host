include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-desktop
PKG_RELEASE:=13
PKG_CONFIG_DEPENDS:=CONFIG_OPENWRT_SYSTEMD CONFIG_WESTON_RDP
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-desktop
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Local Weston desktop with LAN VNC and optional RDP
  DEPENDS:=@TARGET_x86_64 +input-support +video-support +accel-support +weston +@WESTON_VNC +seatd +libpam \
	+kmod-input-evdev +dejavu-fonts-ttf-DejaVuSans \
	+dejavu-fonts-ttf-DejaVuSansMono +openssl-util \
	+shadow-usermod +shadow-useradd +shadow-passwd +tar +WESTON_RDP:winpr-hash
endef

define Package/openwrt-desktop/description
  An ordinary-user desktop sharing the local DRM display over authenticated
  TLS VNC. Run desktop-setup after creating a user and setting its password.
endef

define Package/openwrt-desktop/conffiles
/etc/config/desktop
/etc/pam.d/weston-remote-access
$(if $(CONFIG_OPENWRT_SYSTEMD),/etc/pam.d/openwrt-desktop)
endef

define Build/Compile
endef

define Package/openwrt-desktop/install
	$(INSTALL_DIR) $(1)/etc/config $(1)/etc/init.d $(1)/etc/pam.d
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/usr/libexec $(1)/lib/upgrade/keep.d
	$(INSTALL_DATA) ./files/desktop.config $(1)/etc/config/desktop
	$(INSTALL_BIN) ./files/desktop.init $(1)/etc/init.d/desktop
	$(INSTALL_DATA) ./files/weston-remote-access $(1)/etc/pam.d/weston-remote-access
	$(if $(CONFIG_OPENWRT_SYSTEMD),$(INSTALL_DATA) ./files/openwrt-desktop.pam $(1)/etc/pam.d/openwrt-desktop)
	$(INSTALL_BIN) ./files/desktop-setup $(1)/usr/sbin/desktop-setup
	$(if $(CONFIG_WESTON_RDP),$(INSTALL_BIN) ./files/desktop-rdp-setup $(1)/usr/sbin/desktop-rdp-setup)
	$(INSTALL_BIN) ./files/desktop-dbus-session $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/desktop-session $(1)/usr/libexec/desktop-session
	$(INSTALL_DATA) ./files/desktop-common.sh $(1)/usr/libexec/desktop-common.sh
	$(INSTALL_DATA) ./files/desktop.keep $(1)/lib/upgrade/keep.d/desktop
	$(INSTALL_DIR) $(1)/etc/hotplug.d/drm
	$(INSTALL_BIN) ./files/desktop.hotplug $(1)/etc/hotplug.d/drm/95-desktop
endef

$(eval $(call BuildPackage,openwrt-desktop))
