include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-desktop
PKG_RELEASE:=42
PKG_CONFIG_DEPENDS:=CONFIG_OPENWRT_SYSTEMD
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-desktop-base
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Shared native-systemd desktop launcher and control
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +input-support +video-support +accel-support \
	+systemd-udev +kmod +glibc-locale-utf8 +libpam +kmod-input-evdev \
	+openssl-util +shadow-usermod +shadow-useradd +shadow-passwd +shadow-su \
	+tar +rtkit +python3
endef

define Package/openwrt-desktop-base/description
  Shared native-systemd desktop launcher, PAM/logind VT7 session manager,
  session plugin dispatcher, shared session services, and desktop-ctl CLI.
  Install a desktop session backend (such as openwrt-desktop-core) alongside it.
endef

define Package/openwrt-desktop-base/conffiles
/etc/config/desktop
/etc/pam.d/openwrt-desktop
endef

define Package/openwrt-desktop-keyring
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Shared Secret Service keyring bootstrap helpers for desktops
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +openwrt-desktop-base \
	+gnome-keyring +python3-gobject +glib2-utils
endef

define Package/openwrt-desktop-keyring/description
  Shared TPM2-sealed and plaintext-fallback Secret Service keyring bootstrap
  and unattended unlock helpers used by GNOME and KDE Plasma sessions.
endef

define Package/openwrt-desktop-rdp-base
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Shared LAN RDP provisioning CLI for OpenWrt desktops
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +openwrt-desktop-base +openwrt-desktop-keyring
endef

define Package/openwrt-desktop-rdp-base/description
  Shared desktop-rdp-setup CLI that provisions LAN IPv4 RDP credentials for
  the selected GNOME or KDE Plasma session backend.
endef

define Package/openwrt-desktop-core
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Shared GNOME desktop session (without RDP)
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +openwrt-desktop-base \
	+openwrt-desktop-keyring \
	+gnome-shell +gnome-session +gnome-settings-daemon +gnome-control-center \
	+nautilus +gnome-terminal +gnome-tweaks \
	+wl-clipboard +resources +gnome-text-editor +loupe +gnome-calculator \
	+baobab +file-roller +evince \
	+xdg-desktop-portal-gnome +xwayland \
	+dejavu-fonts-ttf-DejaVuSans +noto-sans-symbols2 \
	+dejavu-fonts-ttf-DejaVuSansMono
endef

define Package/openwrt-desktop-core/description
  An ordinary-user GNOME Wayland session on VT7 without GNOME Remote Desktop.
  Run desktop-setup after creating a user and setting its password.
endef

define Package/openwrt-desktop-rdp
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=LAN RDP remote access for the shared GNOME desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +openwrt-desktop-core \
	+openwrt-desktop-rdp-base +gnome-remote-desktop
endef

define Package/openwrt-desktop-rdp/description
  GNOME Remote Desktop integration and desktop-rdp-setup provisioning tool
  for sharing the local GNOME Wayland display over LAN IPv4 RDP.
endef

define Package/openwrt-desktop
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Shared GNOME desktop with LAN RDP and Sunshine
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +openwrt-desktop-core +openwrt-desktop-rdp +rtkit
endef

define Package/openwrt-desktop/description
  An ordinary-user GNOME session sharing its local display over RDP and
  Sunshine. Run desktop-setup after creating a user and setting its password.
endef

define Build/Compile
endef

define Package/openwrt-desktop-base/install
	$(INSTALL_DIR) $(1)/etc/config $(1)/etc/init.d $(1)/etc/pam.d
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/usr/libexec $(1)/usr/libexec/openwrt-desktop/sessions.d $(1)/lib/upgrade/keep.d
	$(INSTALL_DATA) ./files/desktop.config $(1)/etc/config/desktop
	$(INSTALL_BIN) ./files/desktop.init $(1)/etc/init.d/desktop
	$(INSTALL_DATA) ./files/openwrt-desktop.pam $(1)/etc/pam.d/openwrt-desktop
	$(INSTALL_BIN) ./files/desktop-setup $(1)/usr/sbin/desktop-setup
	$(INSTALL_BIN) ./files/desktop-ctl $(1)/usr/sbin/desktop-ctl
	$(INSTALL_BIN) ./files/desktop-user-setup ./files/desktop-user-stop $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/desktop-session ./files/desktop-session-services $(1)/usr/libexec/
	$(INSTALL_DATA) ./files/desktop-common.sh $(1)/usr/libexec/desktop-common.sh
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system $(1)/usr/lib/systemd/user
	$(INSTALL_DATA) ./files/openwrt-desktop-coldplug.service $(1)/usr/lib/systemd/system/
	$(INSTALL_BIN) ./files/desktop-gpu-coldplug $(1)/usr/libexec/
	$(INSTALL_DATA) ./files/openwrt-desktop-services.service $(1)/usr/lib/systemd/user/
	$(INSTALL_DATA) ./files/desktop.keep $(1)/lib/upgrade/keep.d/desktop
	$(INSTALL_DIR) $(1)/etc/hotplug.d/drm
	$(INSTALL_BIN) ./files/desktop.hotplug $(1)/etc/hotplug.d/drm/95-desktop
	$(INSTALL_DIR) $(1)/usr/lib/apk/commit_hooks.d
	$(INSTALL_BIN) ./files/icon-theme-refresh.hook $(1)/usr/lib/apk/commit_hooks.d/70-icon-theme-refresh
endef

define Package/openwrt-desktop-keyring/install
	$(INSTALL_DIR) $(1)/usr/libexec
	$(INSTALL_BIN) ./files/desktop-keyring-unlock ./files/desktop-keyring-control-unlock ./files/desktop-gnome-keyring-setup $(1)/usr/libexec/
endef

define Package/openwrt-desktop-rdp-base/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) ./files/desktop-rdp-setup $(1)/usr/sbin/desktop-rdp-setup
endef

define Package/openwrt-desktop-core/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/libexec/openwrt-desktop/sessions.d
	$(INSTALL_DATA) ./files/sessions.d/gnome $(1)/usr/libexec/openwrt-desktop/sessions.d/gnome
	$(INSTALL_BIN) ./files/desktop-gnome-remotes ./files/desktop-gnome-settings $(1)/usr/libexec/
	$(INSTALL_DIR) $(1)/usr/lib/systemd/user
	$(INSTALL_DATA) ./files/openwrt-gnome-remotes.service $(1)/usr/lib/systemd/user/
	$(INSTALL_DIR) $(1)/usr/share/glib-2.0/schemas
	$(INSTALL_DATA) ./files/90-openwrt-desktop.gschema.override $(1)/usr/share/glib-2.0/schemas/
endef

define Package/openwrt-desktop-rdp/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/lib/systemd/user/gnome-remote-desktop.service.d
	$(INSTALL_BIN) ./files/desktop-rdp-configure $(1)/usr/libexec/desktop-rdp-configure
	$(INSTALL_DATA) ./files/gnome-rdp-openwrt.conf $(1)/usr/lib/systemd/user/gnome-remote-desktop.service.d/openwrt.conf
endef

define Package/openwrt-desktop/install
	:
endef

$(eval $(call BuildPackage,openwrt-desktop-base))
$(eval $(call BuildPackage,openwrt-desktop-keyring))
$(eval $(call BuildPackage,openwrt-desktop-rdp-base))
$(eval $(call BuildPackage,openwrt-desktop-core))
$(eval $(call BuildPackage,openwrt-desktop-rdp))
$(eval $(call BuildPackage,openwrt-desktop))
