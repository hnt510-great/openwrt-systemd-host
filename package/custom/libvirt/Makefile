include $(TOPDIR)/rules.mk

PKG_NAME:=libvirt
PKG_VERSION:=12.9.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.libvirt.org/
PKG_HASH:=dcf579d8a949f4cbf56820529d48f200382a48ea12855ffded7c16a189353cd7
PKG_LICENSE:=LGPL-2.1-or-later
PKG_LICENSE_FILES:=COPYING.LESSER
PKG_CPE_ID:=cpe:/a:libvirt:libvirt
PKG_INSTALL:=1
PKG_BUILD_PARALLEL:=1
PKG_BUILD_DEPENDS:=python3/host libxml2/host libxslt/host
PKG_CONFIG_DEPENDS:=CONFIG_TARGET_ROOTFS_PERSIST_VAR

# systemd identifies mounts by their canonical path, whereas /var usually
# aliases /tmp on OpenWrt. Keep both filesystem configurations usable.
LIBVIRT_STATE_PATH:=$(if $(CONFIG_TARGET_ROOTFS_PERSIST_VAR),/var,/tmp)/lib/libvirt
LIBVIRT_STATE_UNIT:=$(if $(CONFIG_TARGET_ROOTFS_PERSIST_VAR),var,tmp)-lib-libvirt.mount

MESON_USE_STAGING_PYTHON:=1
include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/meson.mk

define Package/libvirt/Default
  SECTION:=utils
  CATEGORY:=Utilities
  SUBMENU:=Virtualization
  URL:=https://libvirt.org/
  DEPENDS:=@TARGET_x86_64 @USE_GLIBC @OPENWRT_SYSTEMD
endef

define Package/libvirt
  $(call Package/libvirt/Default)
  SECTION:=libs
  CATEGORY:=Libraries
  SUBMENU:=
  TITLE:=Libvirt client and common libraries
  DEPENDS+=+glib2 +libgnutls +libxml2 +libtirpc +libjson-c +libnl-core +libnl-route +libcap-ng +libacl +libbsd
endef

define Package/virsh
  $(call Package/libvirt/Default)
  TITLE:=Libvirt virtual machine command line client
  DEPENDS+=+libvirt +libreadline
endef

define Package/libvirt-daemon
  $(call Package/libvirt/Default)
  TITLE:=Native systemd QEMU and directory storage management
  DEPENDS+=+libvirt +virsh +qemu-x86_64-softmmu +qemu-img +kmod-tun +kvm-support +accel-support
  DEPENDS+=+coreutils-dd +coreutils-kill +coreutils-true +coreutils-timeout
  DEPENDS+=+coreutils-chown +coreutils-chmod +coreutils-mkdir +coreutils-mv +coreutils-rm +coreutils-stat +coreutils-sleep
  DEPENDS+=+acl +shadow-su
  USERID:=libvirt-qemu=191:libvirt-qemu=191:kvm=34,render=43
endef

define Package/libvirt-daemon/conffiles
/etc/libvirt/
/etc/libvirt/libvirt.conf
/etc/libvirt/qemu.conf
/etc/libvirt/qemu-lockd.conf
/etc/libvirt/virtqemud.conf
/etc/libvirt/virtstoraged.conf
/etc/libvirt/virtsecretd.conf
/etc/libvirt/virtlogd.conf
/etc/libvirt/virtlockd.conf
endef

MESON_VARS += PATH="$(STAGING_DIR_HOSTPKG)/bin:$(TARGET_PATH)"
MESON_ARGS += \
	--prefix=/usr --libdir=lib --libexecdir=libexec \
	--sysconfdir=/etc --localstatedir=/var \
	-Dsystem=false -Drunstatedir=/run -Dinitconfdir=/etc/default \
	-Dunitdir=/usr/lib/systemd/system -Dinit_script=systemd \
	-Dauto_features=disabled -Ddefault_library=shared \
	-Ddriver_libvirtd=enabled -Dlibvirtd=disabled \
	-Ddriver_remote=enabled -Dremote_default_mode=direct \
	-Ddriver_qemu=enabled -Ddriver_secret=enabled -Ddriver_storage=enabled -Dstorage_dir=enabled \
	-Ddriver_network=disabled -Ddriver_nwfilter=disabled -Ddriver_interface=disabled \
	-Djson_c=enabled -Dlibnl=enabled -Dcapng=enabled -Dreadline=enabled \
	-Dqemu_user=libvirt-qemu -Dqemu_group=libvirt-qemu \
	-Dqemu_datadir=/usr/share/qemu -Dqemu_moddir=/usr/lib/qemu \
	-Ddocs=disabled -Dtests=disabled -Dnls=disabled \
	-Dgit_werror=disabled -Dwerror=false

define Build/Compile
	$(call Build/Compile/Meson)
	$(INSTALL_DIR) $(MESON_BUILD_DIR)/docs
	$(STAGING_DIR_HOSTPKG)/bin/python3 $(PKG_BUILD_DIR)/scripts/apibuild.py $(PKG_BUILD_DIR)/docs $(MESON_BUILD_DIR)/docs
endef

define Build/InstallDev
	$(INSTALL_DIR) $(1)/usr/include $(1)/usr/lib/pkgconfig
	$(CP) $(PKG_INSTALL_DIR)/usr/include/libvirt $(1)/usr/include/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libvirt*.so* $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/pkgconfig/libvirt*.pc $(1)/usr/lib/pkgconfig/
	$(INSTALL_DIR) $(1)/usr/share/libvirt/api
	$(CP) $(MESON_BUILD_DIR)/docs/*api.xml $(1)/usr/share/libvirt/api/
	$(SED) 's|^libvirt_api=.*|libvirt_api=$(STAGING_DIR)/usr/share/libvirt/api/libvirt-api.xml|;s|^libvirt_qemu_api=.*|libvirt_qemu_api=$(STAGING_DIR)/usr/share/libvirt/api/libvirt-qemu-api.xml|;s|^libvirt_lxc_api=.*|libvirt_lxc_api=$(STAGING_DIR)/usr/share/libvirt/api/libvirt-lxc-api.xml|' $(1)/usr/lib/pkgconfig/libvirt.pc
endef

define Package/libvirt/install
	$(INSTALL_DIR) $(1)/usr/lib
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libvirt*.so.* $(1)/usr/lib/
endef

define Package/virsh/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/bin/virsh $(1)/usr/bin/
endef

define Package/libvirt-daemon/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/usr/lib $(1)/usr/share
	$(INSTALL_DIR) $(1)/etc/libvirt $(1)/usr/libexec
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system $(1)/etc/systemd/system/multi-user.target.wants
	$(CP) $(PKG_INSTALL_DIR)/usr/lib/libvirt $(1)/usr/lib/
	$(CP) $(PKG_INSTALL_DIR)/usr/share/libvirt $(1)/usr/share/
	$(CP) $(PKG_INSTALL_DIR)/etc/libvirt/. $(1)/etc/libvirt/
	for daemon in virtqemud virtstoraged virtsecretd virtlogd virtlockd; do \
		$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/sbin/$$$$daemon $(1)/usr/sbin/; \
		$(CP) $(PKG_INSTALL_DIR)/usr/lib/systemd/system/$$$$daemon*.service \
			$(PKG_INSTALL_DIR)/usr/lib/systemd/system/$$$$daemon*.socket $(1)/usr/lib/systemd/system/; \
		$(INSTALL_DIR) $(1)/usr/lib/systemd/system/$$$$daemon.service.d; \
		$(INSTALL_DATA) ./files/daemon.conf $(1)/usr/lib/systemd/system/$$$$daemon.service.d/openwrt.conf; \
		for socket in $(PKG_INSTALL_DIR)/usr/lib/systemd/system/$$$$daemon*.socket; do \
			unit=$$$${socket##*/}; \
			$(INSTALL_DIR) $(1)/usr/lib/systemd/system/$$$$unit.d; \
			$(INSTALL_DATA) ./files/socket.conf $(1)/usr/lib/systemd/system/$$$$unit.d/openwrt.conf; \
		done; \
		$(LN) /usr/lib/systemd/system/$$$$daemon.socket $(1)/etc/systemd/system/multi-user.target.wants/; \
	done
	$(INSTALL_DATA) ./files/*.service $(1)/usr/lib/systemd/system/
	$(INSTALL_DATA) ./files/var-lib-libvirt.mount $(1)/usr/lib/systemd/system/$(LIBVIRT_STATE_UNIT)
	$(SED) 's,^Where=.*,Where=$(LIBVIRT_STATE_PATH),' $(1)/usr/lib/systemd/system/$(LIBVIRT_STATE_UNIT)
	$(INSTALL_DIR) $(1)/usr/lib/systemd/system/virtqemud.service.d
	$(INSTALL_DATA) ./files/qemu-service.conf $(1)/usr/lib/systemd/system/virtqemud.service.d/qemu.conf
	$(INSTALL_DATA) ./files/secret-service.conf $(1)/usr/lib/systemd/system/virtsecretd.service.d/secret.conf
	$(SED) 's,var-lib-libvirt.mount,$(LIBVIRT_STATE_UNIT),g' \
		$(1)/usr/lib/systemd/system/*.service \
		$(1)/usr/lib/systemd/system/virt*.d/*.conf
	$(INSTALL_DATA) ./files/qemu.conf $(1)/etc/libvirt/qemu.conf
	$(INSTALL_DATA) ./files/libvirt.conf $(1)/etc/libvirt/libvirt.conf
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/usr/libexec/libvirt_iohelper $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/libvirt-openwrt-prepare ./files/libvirt-openwrt-guests ./files/libvirt-pipewire-access $(1)/usr/libexec/
	$(INSTALL_DATA) ./files/libvirt-pipewire-access@.path $(1)/usr/lib/systemd/system/
	$(INSTALL_DIR) $(1)/etc/hotplug.d/drm
	$(INSTALL_BIN) ./files/libvirt-render.hotplug $(1)/etc/hotplug.d/drm/zz-libvirt-render
	$(LN) /usr/lib/systemd/system/virtqemud.service $(1)/etc/systemd/system/multi-user.target.wants/
	$(LN) /usr/lib/systemd/system/libvirt-openwrt-guests.service $(1)/etc/systemd/system/multi-user.target.wants/
	$(INSTALL_DIR) $(1)/usr/share/libvirt/examples
	$(INSTALL_DATA) ./files/openwrt*.xml $(1)/usr/share/libvirt/examples/
	$(INSTALL_DIR) $(1)/usr/lib/upgrade/keep.d
	$(INSTALL_DATA) ./files/libvirt.keep $(1)/usr/lib/upgrade/keep.d/libvirt
endef

$(eval $(call BuildPackage,libvirt))
$(eval $(call BuildPackage,virsh))
$(eval $(call BuildPackage,libvirt-daemon))
