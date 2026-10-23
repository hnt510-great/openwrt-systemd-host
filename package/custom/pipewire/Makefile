include $(TOPDIR)/rules.mk

PKG_NAME:=pipewire
PKG_VERSION:=1.6.10
PKG_RELEASE:=1
PKG_BUILD_DIR:=$(BUILD_DIR)/pipewire-$(PKG_VERSION)
PKG_SOURCE:=pipewire-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/PipeWire/pipewire/tar.gz/refs/tags/$(PKG_VERSION)?
PKG_HASH:=93b7c4f1e62fd9ec3a921846c6bfc64442872bb2366c2bbc3ea69a427b79a4f9
PKG_LICENSE:=MIT
PKG_LICENSE_FILES:=COPYING
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=glib2/host

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/libpipewire
  SECTION:=libs
  CATEGORY:=Libraries
  TITLE:=PipeWire multimedia client library
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +libpthread +librt +libdbus +libsystemd
endef

define Package/pipewire
  SECTION:=sound
  CATEGORY:=Sound
  TITLE:=PipeWire desktop audio server
  DEPENDS:=+libpipewire +alsa-lib +libudev-zero +alsa-ucm-conf +libsndfile +glib2
endef

define Package/pipewire-pulse
  SECTION:=sound
  CATEGORY:=Sound
  TITLE:=PipeWire PulseAudio protocol server
  DEPENDS:=+pipewire
  CONFLICTS:=pulseaudio-daemon pulseaudio-daemon-avahi
endef

define Package/pipewire-alsa
  SECTION:=sound
  CATEGORY:=Sound
  TITLE:=ALSA applications through PipeWire
  DEPENDS:=+pipewire
endef

define Package/pipewire-tools
  SECTION:=sound
  CATEGORY:=Sound
  TITLE:=PipeWire playback, recording and diagnostic tools
  DEPENDS:=+pipewire +libncurses
endef

MESON_ARGS += --prefix=/usr --libdir=lib --sysconfdir=/etc --localstatedir=/var \
	-Ddefault_library=shared --wrap-mode=nodownload -Dauto_features=disabled -Dexamples=disabled \
	-Dtests=disabled -Dinstalled_tests=disabled -Dpipewire-jack=disabled -Dpipewire-v4l2=disabled \
	-Dspa-plugins=enabled -Dsupport=enabled -Dsession-managers=[] -Dpam-defaults-install=false \
	-Drlimits-install=false -Dalsa=enabled -Dudev=enabled -Ddbus=enabled \
	-Daudiomixer=enabled -Daudioconvert=enabled -Daudiotestsrc=enabled \
	-Dlibsystemd=enabled -Dlogind=enabled -Dsystemd-user-service=enabled \
	-Dsystemd-user-unit-dir=/usr/lib/systemd/user -Dsystemd-system-service=disabled \
	-Dpipewire-alsa=enabled -Dsndfile=enabled -Dpw-cat=enabled -Dflatpak=enabled

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/. $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/*.pc $(1)/usr/lib/pkgconfig/
endef

define Package/libpipewire/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/*.so.* $(1)/usr/lib/
	$(INSTALL_DIR) $(1)/usr/lib/spa-0.2/support
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/spa-0.2/support/*.so $(1)/usr/lib/spa-0.2/support/
	$(INSTALL_DIR) $(1)/usr/share/pipewire $(1)/usr/lib/pipewire-0.3
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/pipewire/client.conf $(1)/usr/share/pipewire/
	for module in protocol-native client-node client-device adapter metadata session-manager; do \
		$(CP) $(PKG_INSTALL_DIR)/usr/lib/pipewire-0.3/libpipewire-module-$$$$module.so \
			$(1)/usr/lib/pipewire-0.3/; \
	done
endef

define Package/pipewire/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib/pipewire-0.3 $(1)/usr/lib/spa-0.2 $(1)/usr/share/pipewire
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/pipewire $(1)/usr/bin/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pipewire-0.3/*.so $(1)/usr/lib/pipewire-0.3/
	for module in protocol-native client-node client-device adapter metadata session-manager protocol-pulse; do \
		rm -f $(1)/usr/lib/pipewire-0.3/libpipewire-module-$$$$module.so; \
	done
	for plugin in alsa audioconvert audiomixer audiotestsrc; do \
		$(CP) $(PKG_INSTALL_DIR)/usr/lib/spa-0.2/$$$$plugin $(1)/usr/lib/spa-0.2/; \
	done
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/pipewire/pipewire.conf $(1)/usr/share/pipewire/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/alsa-card-profile $(1)/usr/share/
	$(INSTALL_DIR) $(1)/usr/lib/systemd/user
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/systemd/user/pipewire.service \
		$(PKG_INSTALL_DIR)/usr/lib/systemd/user/pipewire.socket $(1)/usr/lib/systemd/user/
endef

define Package/pipewire-pulse/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/usr/lib/pipewire-0.3 $(1)/usr/share/pipewire $(1)/usr/lib/systemd/user
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/pipewire-pulse $(1)/usr/bin/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/pipewire-0.3/libpipewire-module-protocol-pulse.so $(1)/usr/lib/pipewire-0.3/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/share/pipewire/pipewire-pulse.conf $(1)/usr/share/pipewire/
	$(INSTALL_DATA) $(PKG_INSTALL_DIR)/usr/lib/systemd/user/pipewire-pulse.service \
		$(PKG_INSTALL_DIR)/usr/lib/systemd/user/pipewire-pulse.socket $(1)/usr/lib/systemd/user/
endef

define Package/pipewire-alsa/install
	$(INSTALL_DIR) $(1)/usr/lib/alsa-lib $(1)/usr/share/alsa/alsa.conf.d
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/alsa-lib/libasound_module_*_pipewire.so $(1)/usr/lib/alsa-lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/alsa/alsa.conf.d/*pipewire* $(1)/usr/share/alsa/alsa.conf.d/
	$(INSTALL_DIR) $(1)/etc/alsa/conf.d
	$(LN) /usr/share/alsa/alsa.conf.d/50-pipewire.conf $(1)/etc/alsa/conf.d/50-pipewire.conf
	$(LN) /usr/share/alsa/alsa.conf.d/99-pipewire-default.conf $(1)/etc/alsa/conf.d/99-pipewire-default.conf
endef

define Package/pipewire-tools/install
	$(INSTALL_DIR) $(1)/usr/bin
	for tool in pw-cat pw-cli pw-dump pw-link pw-loopback pw-metadata pw-profiler pw-top; do \
		$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/$$$$tool $(1)/usr/bin/; \
	done
	$(LN) pw-cat $(1)/usr/bin/pw-play
	$(LN) pw-cat $(1)/usr/bin/pw-record
endef

$(eval $(call BuildPackage,libpipewire))
$(eval $(call BuildPackage,pipewire))
$(eval $(call BuildPackage,pipewire-pulse))
$(eval $(call BuildPackage,pipewire-alsa))
$(eval $(call BuildPackage,pipewire-tools))
