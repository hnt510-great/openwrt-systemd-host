include $(TOPDIR)/rules.mk

PKG_NAME:=openwrt-desktop-audio
PKG_VERSION:=1
PKG_RELEASE:=1
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/openwrt-desktop-audio
  SECTION:=sound
  CATEGORY:=Sound
  TITLE:=Ordinary-user desktop and remote audio integration
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD +openwrt-desktop \
	+pipewire +pipewire-pulse +pipewire-alsa +pipewire-tools +wireplumber \
	+gstreamer1-utils +audio-support +libpulse +pulseaudio-tools +alsa-ucm-conf +alsa-utils +acl \
	+@PACKAGE_gstreamer1-plugins-good +@PACKAGE_gstreamer1-plugins-bad \
	+gst1-mod-app +gst1-mod-audioconvert +gst1-mod-audioresample \
	+gst1-mod-audiotestsrc +gst1-mod-autodetect +gst1-mod-playback +gst1-mod-pulse \
	+gst1-mod-id3demux +gst1-mod-typefindfunctions +gst1-mod-audioparsers +gst1-mod-ogg \
	+gst1-mod-opus +gst1-mod-vorbis +gst1-mod-flac +gst1-mod-mpg123 \
	+gst1-mod-faad +gst1-mod-wavparse +gst1-mod-wavenc +gst1-mod-isomp4
endef

define Build/Compile
endef

define Package/openwrt-desktop-audio/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/usr/bin $(1)/usr/libexec $(1)/usr/lib/systemd/user
	$(INSTALL_BIN) ./files/desktop-audio-setup $(1)/usr/sbin/
	$(INSTALL_BIN) ./files/desktop-audio-stream $(1)/usr/bin/
	$(INSTALL_BIN) ./files/desktop-audio-session $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/desktop-audio-permissions $(1)/usr/libexec/
	$(INSTALL_DIR) $(1)/etc/init.d $(1)/etc/hotplug.d/sound
	$(INSTALL_BIN) ./files/desktop-audio-permissions.init $(1)/etc/init.d/desktop-audio-permissions
	$(INSTALL_BIN) ./files/desktop-audio.hotplug $(1)/etc/hotplug.d/sound/95-desktop-audio
	$(INSTALL_DATA) ./files/openwrt-audio-session.target $(1)/usr/lib/systemd/user/
endef

$(eval $(call BuildPackage,openwrt-desktop-audio))
