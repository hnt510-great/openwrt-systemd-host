include $(TOPDIR)/rules.mk

PKG_NAME:=ovmf-bin
# Updated by scripts/update-custom-packages.py from the Debian edk2 pool.
PKG_VERSION:=2026.08
PKG_RELEASE:=1
PKG_SOURCE_VERSION:=2026.08+ds-3

PKG_SOURCE:=ovmf-generic_$(PKG_SOURCE_VERSION)_all.deb
PKG_SOURCE_URL:=https://deb.debian.org/debian/pool/main/e/edk2/ \
	https://ftp.debian.org/debian/pool/main/e/edk2/
PKG_HASH:=0ee404cbf543ce0077c159a946fa8012b779b94a8c158678dc94f290fbd67eea
PKG_BUILD_DIR:=$(BUILD_DIR)/ovmf-generic-$(PKG_SOURCE_VERSION)

PKG_LICENSE:=BSD-2-Clause-Patent
PKG_LICENSE_FILES:=usr/share/doc/ovmf-generic/copyright

include $(INCLUDE_DIR)/package.mk

define Package/ovmf-bin
  SECTION:=utils
  CATEGORY:=Utilities
  SUBMENU:=Virtualization
  TITLE:=UEFI firmware for x86_64 virtual machines (Debian OVMF build)
  URL:=https://www.tianocore.org/
  DEPENDS:=@TARGET_x86_64
  PKGARCH:=all
endef

define Package/ovmf-bin/description
  Debian's prebuilt OVMF (EDK II) firmware for x86_64 QEMU guests: plain UEFI,
  Secure Boot with an empty variable store, and Secure Boot with the Microsoft
  keys enrolled. QEMU firmware descriptors let libvirt select it with
  <os firmware='efi'>.
endef

define Build/Prepare
	$(INSTALL_DIR) $(PKG_BUILD_DIR)
	cd $(PKG_BUILD_DIR) && ar p $(DL_DIR)/$(PKG_SOURCE) data.tar.xz | $(HOST_TAR) -xJf -
endef

define Build/Compile
endef

define Package/ovmf-bin/install
	$(INSTALL_DIR) $(1)/usr/share/OVMF $(1)/usr/share/qemu/firmware $(1)/usr/share/doc/ovmf-bin
	$(INSTALL_DATA) \
		$(PKG_BUILD_DIR)/usr/share/OVMF/OVMF_CODE_4M.fd \
		$(PKG_BUILD_DIR)/usr/share/OVMF/OVMF_CODE_4M.secboot.fd \
		$(PKG_BUILD_DIR)/usr/share/OVMF/OVMF_VARS_4M.fd \
		$(PKG_BUILD_DIR)/usr/share/OVMF/OVMF_VARS_4M.ms.fd \
		$(1)/usr/share/OVMF/
	$(LN) OVMF_CODE_4M.secboot.fd $(1)/usr/share/OVMF/OVMF_CODE_4M.ms.fd
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/usr/share/qemu/firmware/*-edk2-x86_64*.json $(1)/usr/share/qemu/firmware/
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/usr/share/doc/ovmf-generic/copyright $(1)/usr/share/doc/ovmf-bin/
endef

$(eval $(call BuildPackage,ovmf-bin))
