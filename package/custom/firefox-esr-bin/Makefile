include $(TOPDIR)/rules.mk

PKG_NAME:=firefox-esr-bin
PKG_VERSION:=153.5.0esr
PKG_RELEASE:=1
PKG_SOURCE:=firefox-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://archive.mozilla.org/pub/firefox/releases/$(PKG_VERSION)/linux-x86_64/zh-CN/
PKG_HASH:=8d1fe8dee18785ee7f0249589cf240ad7f81f4cad8e450b1c6fce5138a702dc2
PKG_BUILD_DIR:=$(BUILD_DIR)/firefox-esr-$(PKG_VERSION)
PKG_UNPACK:=mkdir -p $(PKG_BUILD_DIR)/upstream; xzcat $(DL_DIR)/$(PKG_SOURCE) | $(TAR) -C $(PKG_BUILD_DIR)/upstream --strip-components=1 -xf -
PKG_LICENSE:=MPL-2.0 GPL-2.0-or-later LGPL-2.1-or-later
# The official archive carries its complete about:license document in omni.ja.
PKG_LICENSE_FILES:=

include $(INCLUDE_DIR)/package.mk

# Keep the upstream executable payload intact, including private bundled libraries.
STRIP:=:
RSTRIP:=:

define Package/firefox-esr-bin
  SECTION:=utils
  CATEGORY:=Utilities
  SUBMENU:=Browsers
  TITLE:=Mozilla Firefox ESR (official Simplified Chinese build)
  # APK's version grammar does not accept Mozilla's literal "esr" suffix.
  VERSION:=$(patsubst %esr,%,$(PKG_VERSION))-r$(PKG_RELEASE)
  URL:=https://www.firefox.com/
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +audio-support +glibc-distro-compat +libgtk3 +dbus \
	+ca-bundle +fontconfig +dejavu-fonts-ttf-DejaVuSans +noto-sans-cjk-sc \
	+alsa-lib +libffmpeg +libX11 +libXext +libXrender +libXrandr +libXi \
	+libXcursor +libXfixes +libXdamage +libXcomposite +libxcb
endef

define Package/firefox-esr-bin/description
  Mozilla's official x86_64 glibc Firefox ESR build with Chinese UI, private
  bundled libraries, native Wayland launchers and software video decoding.
  Run as an ordinary desktop user. Updates are managed by APK or firmware.
endef

define Build/Configure
endef

define Build/Compile
endef

define Package/firefox-esr-bin/install
	$(INSTALL_DIR) $(1)/usr/lib/firefox-esr $(1)/usr/bin $(1)/usr/share/applications
	$(CP) $(PKG_BUILD_DIR)/upstream/. $(1)/usr/lib/firefox-esr/
	$(INSTALL_BIN) ./files/firefox-esr $(1)/usr/bin/firefox-esr
	$(LN) firefox-esr $(1)/usr/bin/firefox
	$(INSTALL_DATA) ./files/firefox-esr.desktop $(1)/usr/share/applications/
	$(INSTALL_DIR) $(1)/usr/lib/firefox-esr/distribution $(1)/usr/lib/firefox-esr/defaults/pref
	$(INSTALL_DATA) ./files/policies.json $(1)/usr/lib/firefox-esr/distribution/
	$(INSTALL_DATA) ./files/openwrt.js $(1)/usr/lib/firefox-esr/defaults/pref/
	for size in 16 32 48 64 128; do \
		$(INSTALL_DIR) $(1)/usr/share/icons/hicolor/$$$${size}x$$$${size}/apps; \
		$(INSTALL_DATA) $(PKG_BUILD_DIR)/upstream/browser/chrome/icons/default/default$$$${size}.png \
			$(1)/usr/share/icons/hicolor/$$$${size}x$$$${size}/apps/firefox-esr.png; \
	done
endef

$(eval $(call BuildPackage,firefox-esr-bin))
