include $(TOPDIR)/rules.mk

PKG_NAME:=gnome-remote-desktop
PKG_VERSION:=51.0
PKG_RELEASE:=7
PKG_SOURCE:=gnome-remote-desktop-51.0.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gnome-remote-desktop/51/
PKG_HASH:=c7954b34da5766288ea19b56026421c9c1fe2c23ef379e57ec209dc0cf13df2b
PKG_LICENSE:=GPL-2.0-or-later
PKG_BUILD_DEPENDS:=glslang/host spirv-tools/host nv-codec-headers
GNOME_TITLE:=GNOME shared-session RDP server
GNOME_DEPENDS:=+glib2 +libcairo +libdrm +libepoxy +libei +libnotify +libsecret +libsystemd +krb5-libs +libpipewire +tpm2-tss +libxkbcommon +fdk-aac +libfreerdp3 +libfuse3 +libva +libopus +polkit +vulkan-loader
GNOME_MESON_ARGS:=-Drdp=true -Dvnc=false -Dman=false -Dtests=false -Dsystemd=true -Dsystemd_user_unit_dir=/usr/lib/systemd/user -Dsystemd_system_unit_dir=/usr/lib/systemd/system -Dsystemd_sysusers_dir=/usr/lib/sysusers.d -Dsystemd_tmpfiles_dir=/usr/lib/tmpfiles.d

include $(INCLUDE_DIR)/gnome-package.mk

# This profile shares the active user session. Do not expose GDM remote login
# or the independent headless/handover services through systemd or D-Bus.
define Build/Install
	$(call Build/Install/Meson)
	$(RM) -r $(PKG_INSTALL_DIR)/usr/lib/systemd/system \
		$(PKG_INSTALL_DIR)/usr/lib/sysusers.d $(PKG_INSTALL_DIR)/usr/lib/tmpfiles.d \
		$(PKG_INSTALL_DIR)/usr/share/dbus-1/system.d $(PKG_INSTALL_DIR)/usr/share/dbus-1/system-services \
		$(PKG_INSTALL_DIR)/usr/share/polkit-1
	$(RM) $(PKG_INSTALL_DIR)/usr/lib/systemd/user/gnome-remote-desktop-{headless,handover}.service \
		$(PKG_INSTALL_DIR)/usr/libexec/gnome-remote-desktop-configuration-daemon \
		$(PKG_INSTALL_DIR)/usr/libexec/grd-pcscd
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
