include $(TOPDIR)/rules.mk

PKG_NAME:=virtiofsd
PKG_VERSION:=1.14.0
PKG_RELEASE:=1

PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION)-vendor.tar.zst
PKG_SOURCE_URL:=@OPENWRT
PKG_SOURCE_PROTO:=cargo-vendor-archive
PKG_VENDOR_FILE:=$(PKG_NAME)-v$(PKG_VERSION).tar.gz
PKG_VENDOR_URL:=https://gitlab.com/virtio-fs/virtiofsd/-/archive/v$(PKG_VERSION)/
PKG_VENDOR_HASH:=52b66e449ca583b4f050a2bff327ff812211a2c349b4130279fcfc6a64540f04
PKG_HASH:=12ec4bb117c743d6891c74bb774200ed8df408f636fb90e683c43aa675505af0

PKG_LICENSE:=Apache-2.0 BSD-3-Clause
PKG_LICENSE_FILES:=LICENSE-APACHE LICENSE-BSD-3-Clause
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/rust-package.mk

# Link the target libseccomp and libcap-ng shared libraries from staging.
CARGO_RUSTFLAGS+=-Lnative=$(STAGING_DIR)/usr/lib
CARGO_PKG_VARS+= \
	LIBSECCOMP_LIB_PATH=$(STAGING_DIR)/usr/lib \
	LIBSECCOMP_LINK_TYPE=dylib

define Package/virtiofsd
  SECTION:=utils
  CATEGORY:=Utilities
  SUBMENU:=Virtualization
  TITLE:=virtio-fs vhost-user file system daemon
  URL:=https://virtio-fs.gitlab.io/
  DEPENDS:=$(RUST_PKG_DEPENDS) @(x86_64||aarch64) +libseccomp +libcap-ng
endef

define Package/virtiofsd/description
  virtiofsd shares a host directory with QEMU guests over virtio-fs.
  QEMU connects to it as a vhost-user-fs device; libvirt discovers it
  through its QEMU vhost-user descriptor and starts one daemon per
  <filesystem driver type='virtiofs'/> guest device.
endef

define Package/virtiofsd/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/usr/share/qemu/vhost-user
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/bin/virtiofsd $(1)/usr/libexec/
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/50-virtiofsd.json $(1)/usr/share/qemu/vhost-user/
endef

$(eval $(call BuildPackage,virtiofsd))
