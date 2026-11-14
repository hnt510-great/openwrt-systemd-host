include $(TOPDIR)/rules.mk

PKG_NAME:=google-chrome-bin
PKG_VERSION:=157.0.8103.78
PKG_RELEASE:=1
PKG_SOURCE:=google-chrome-stable_$(PKG_VERSION)-1_amd64.deb
PKG_SOURCE_URL:=https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/
PKG_HASH:=4d740636b5c96f687798602c5aad6a5a270f44dd02e48db0638ae77aa4867b1b
PKG_BUILD_DIR:=$(BUILD_DIR)/google-chrome-$(PKG_VERSION)
PKG_UNPACK:=rm -rf $(PKG_BUILD_DIR)/deb $(PKG_BUILD_DIR)/upstream; \
	mkdir -p $(PKG_BUILD_DIR)/deb $(PKG_BUILD_DIR)/upstream; \
	(cd $(PKG_BUILD_DIR)/deb && ar x $(DL_DIR)/$(PKG_SOURCE)); \
	$(TAR) -C $(PKG_BUILD_DIR)/upstream -xf $(PKG_BUILD_DIR)/deb/data.tar.*
PKG_LICENSE:=Proprietary
# Google Chrome Terms of Service; third-party notices are shown at chrome://credits.
PKG_LICENSE_FILES:=

include $(INCLUDE_DIR)/package.mk

# Keep Google's signed executable payload and bundled libraries intact.
STRIP:=:
RSTRIP:=:

CHROME_DIR:=opt/google/chrome
# Optional Qt UI shims need Qt, which this firmware does not ship; Chrome falls
# back to GTK. The setuid helper is unused when user namespaces are available.
CHROME_EXCLUDE:=chrome-sandbox cron apparmor.d libqt5_shim.so libqt6_shim.so

define Package/google-chrome-bin
  SECTION:=utils
  CATEGORY:=Utilities
  SUBMENU:=Browsers
  TITLE:=Google Chrome (official stable build)
  URL:=https://www.google.com/chrome/
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC +audio-support +bash +ca-bundle +fontconfig \
	+dejavu-fonts-ttf-DejaVuSans +noto-sans-cjk-sc +glib2-core +glib2-gobject +glib2-gio \
	+libgtk3 +libnss +nspr +at-spi2-core +libdbus +libcups-runtime +libexpat +libgcc \
	+libpthread +libxcb +libxkbcommon +alsa-lib +libpulse +libmesa +libX11 +libXext \
	+libXcomposite +libXdamage +libXfixes +libXrandr +libcairo +libpango +libudev-systemd \
	+libva +intel-media-driver
endef

define Package/google-chrome-bin/description
  Google's official x86_64 glibc Chrome stable build, repackaged from the
  signed Debian archive with its bundled private libraries unchanged.
  Runs natively on Wayland as an ordinary desktop user. Updates are managed
  by APK or firmware; Google's apt repository cron job is not installed.
endef

define Build/Configure
endef

define Build/Compile
endef

define Package/google-chrome-bin/install
	$(INSTALL_DIR) $(1)/$(CHROME_DIR) $(1)/usr/bin $(1)/usr/share/applications
	$(CP) $(PKG_BUILD_DIR)/upstream/$(CHROME_DIR)/. $(1)/$(CHROME_DIR)/
	rm -rf $(addprefix $(1)/$(CHROME_DIR)/,$(CHROME_EXCLUDE))
	$(INSTALL_BIN) ./files/google-chrome-stable $(1)/usr/bin/google-chrome-stable
	$(LN) google-chrome-stable $(1)/usr/bin/google-chrome
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/upstream/usr/share/applications/google-chrome.desktop \
		$(PKG_BUILD_DIR)/upstream/usr/share/applications/com.google.Chrome.desktop \
		$(1)/usr/share/applications/
	$(INSTALL_DIR) $(1)/usr/share/metainfo $(1)/usr/share/gnome-control-center/default-apps
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/upstream/usr/share/appdata/google-chrome.appdata.xml \
		$(1)/usr/share/metainfo/
	$(CP) $(PKG_BUILD_DIR)/upstream/usr/share/gnome-control-center/default-apps/. \
		$(1)/usr/share/gnome-control-center/default-apps/
	for size in 16 24 32 48 64 128 256; do \
		$(INSTALL_DIR) $(1)/usr/share/icons/hicolor/$$$${size}x$$$${size}/apps; \
		$(INSTALL_DATA) $(PKG_BUILD_DIR)/upstream/$(CHROME_DIR)/product_logo_$$$${size}.png \
			$(1)/usr/share/icons/hicolor/$$$${size}x$$$${size}/apps/google-chrome.png; \
	done
endef

$(eval $(call BuildPackage,google-chrome-bin))
