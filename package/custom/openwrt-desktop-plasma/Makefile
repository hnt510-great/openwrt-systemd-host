include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-desktop-plasma
PKG_VERSION:=1
PKG_RELEASE:=6
PKG_CONFIG_DEPENDS:=CONFIG_OPENWRT_SYSTEMD
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-desktop-plasma-core
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Shared KDE Plasma 6.8 Wayland desktop session (without RDP)
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +openwrt-desktop-base \
	+openwrt-desktop-keyring +kwin +plasma-workspace +plasma-desktop \
	+breeze +qqc2-breeze-style +kscreenlocker +polkit-kde-agent-1 \
	+xdg-desktop-portal-kde +plasma-integration +kde-cli-tools \
	+qt6quick-qml-mod-qtcore +qt6quick-qml-mod-qtnetwork \
	+qt6quick-qml-mod-qtqml-xmllistmodel +qt6quick-qml-mod-qtquick-dialogs \
	+qt6quick-qml-mod-qtquick-particles +qt6quick-qml-mod-qtlabs-qmlmodels \
	+qt6quick-qml-mod-qtlabs-platform +qt6quick-qml-mod-qtlabs-settings \
	+qt6quick-qml-mod-qtlabs-folderlistmodel +qt6quick-qml-mod-qtlabs-animation \
	+qt6quick-qml-mod-qtlabs-sharedimage \
	+xwayland +wl-clipboard +dejavu-fonts-ttf-DejaVuSans \
	+noto-sans-symbols2 +dejavu-fonts-ttf-DejaVuSansMono
endef

define Package/openwrt-desktop-plasma-core/description
  An ordinary-user KDE Plasma 6.8 Wayland session on VT7 using KWin,
  shared Secret Service keyring unlock, and OpenWrt desktop session plugin.
endef

define Package/openwrt-desktop-plasma
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Shared KDE Plasma 6.8 daily desktop metapackage
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +openwrt-desktop-plasma-core \
	+systemsettings +kscreen +dolphin +konsole +openwrt-desktop-audio \
	+plasma-pa +openwrt-desktop-ime-plasma
endef

define Package/openwrt-desktop-plasma/description
  Daily KDE Plasma 6.8 desktop installation with System Settings, KScreen,
  Dolphin, Konsole, PipeWire/Plasma audio, and Fcitx5 Chinese Pinyin IME.
endef

define Package/openwrt-desktop-plasma-rdp
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=LAN RDP remote access for the shared KDE Plasma desktop
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +openwrt-desktop-plasma-core \
	+openwrt-desktop-rdp-base +krdp +openwrt-desktop-audio
endef

define Package/openwrt-desktop-plasma-rdp/description
  KDE KRdp integration, LAN-bound wrapper drop-in, and credential helper
  for sharing the local KDE Plasma Wayland display and audio over LAN IPv4 RDP.
endef

define Build/Compile
endef

define Package/openwrt-desktop-plasma-core/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/libexec/openwrt-desktop/sessions.d
	$(INSTALL_DATA) ./files/sessions.d/plasma $(1)/usr/libexec/openwrt-desktop/sessions.d/plasma
	$(INSTALL_BIN) ./files/desktop-plasma-settings ./files/desktop-plasma-remotes $(1)/usr/libexec/
	$(INSTALL_DIR) $(1)/usr/lib/systemd/user
	$(INSTALL_DATA) ./files/openwrt-plasma-remotes.service $(1)/usr/lib/systemd/user/
	$(INSTALL_DIR) $(1)/etc/xdg/xdg-desktop-portal
	$(INSTALL_DATA) ./files/kde-portals.conf $(1)/etc/xdg/xdg-desktop-portal/kde-portals.conf
endef

define Package/openwrt-desktop-plasma/install
	:
endef

define Package/openwrt-desktop-plasma-rdp/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/lib/systemd/user/app-org.kde.krdpserver.service.d
	$(INSTALL_BIN) ./files/desktop-plasma-rdp-configure ./files/desktop-krdp-wrapper $(1)/usr/libexec/
	$(INSTALL_DATA) ./files/krdp-openwrt.conf $(1)/usr/lib/systemd/user/app-org.kde.krdpserver.service.d/openwrt.conf
endef

$(eval $(call BuildPackage,openwrt-desktop-plasma-core))
$(eval $(call BuildPackage,openwrt-desktop-plasma))
$(eval $(call BuildPackage,openwrt-desktop-plasma-rdp))
