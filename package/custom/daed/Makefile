include $(TOPDIR)/rules.mk

PKG_NAME:=daed
PKG_VERSION:=2.1.1
PKG_RELEASE:=2

# daed v2.1.1 bundles a dae core from 2026-04-22 (85a1fc3, before dae
# v2.0.0rc1). This build re-pins the core to the dae v2.1.1 release instead,
# using the dae-wing commit that upstream made for exactly that bump, and keeps
# the daed v2.1.1 dashboard. See docs/daed.md.
#
# Primary source: dae-wing b089b56 "bump dae-core to v2.1.1 and follow its
# control plane API" (dae-wing main after daed v2.1.1).
DAED_WING_COMMIT:=b089b568649f03f909477adb6c7db25535a58782
PKG_SOURCE:=dae-wing-$(DAED_WING_COMMIT).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/daeuniverse/dae-wing/tar.gz/
PKG_SOURCE_URL_FILE:=$(DAED_WING_COMMIT)
PKG_HASH:=406119814907ea34dfa935b6f1ba925d887992e351da746f1ff7a206a6f2a21b

# dae core: the v2.1.1 release source, including the BPF headers submodule.
# patches/ adds three later upstream fixes on top, plus a local dae-wing
# default LAN interface for new configs (004).
DAED_CORE_VERSION:=2.1.1
DAED_CORE_HASH:=7c91494a999a24e91869e8e20e26ed8171dd4eedbcb847d1b04d15a6aeb54f44

# Prebuilt dashboard of the daed v2.1.1 release.
DAED_WEB_HASH:=7eb8f42d4860ab7311f87bda2a921bad34a6d54db7edad47466dcb8d9382fea8

PKG_MAINTAINER:=daeuniverse <https://github.com/daeuniverse/daed>
PKG_LICENSE:=AGPL-3.0-only
PKG_LICENSE_FILES:=LICENSE dae-core/LICENSE

PKG_BUILD_DEPENDS:=golang/host
PKG_BUILD_PARALLEL:=1

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/bpf.mk
include $(TOPDIR)/feeds/packages/lang/golang/golang-package.mk

TAR_CMD=$(HOST_TAR) -C $(PKG_BUILD_DIR) --strip-components=1 $(TAR_OPTIONS)

DAED_CORE_FILE:=dae-$(DAED_CORE_VERSION)-full-src.tar.xz
DAED_WEB_FILE:=$(PKG_NAME)-web-$(PKG_VERSION).zip
DAED_CORE_DIR:=$(PKG_BUILD_DIR)/dae-core
DAED_MAX_MATCH_SET_LEN:=1024

define Download/dae-core
  URL:=https://github.com/daeuniverse/dae/releases/download/v$(DAED_CORE_VERSION)/
  URL_FILE:=dae-full-src.tar.xz
  FILE:=$(DAED_CORE_FILE)
  HASH:=$(DAED_CORE_HASH)
endef

define Download/daed-web
  URL:=https://github.com/daeuniverse/daed/releases/download/v$(PKG_VERSION)/
  URL_FILE:=web.zip
  FILE:=$(DAED_WEB_FILE)
  HASH:=$(DAED_WEB_HASH)
endef

define Package/daed/Default
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Web Servers/Proxies
  URL:=https://github.com/daeuniverse/daed
endef

define Package/daed
  $(call Package/daed/Default)
  TITLE:=dae eBPF transparent proxy with a web dashboard
  DEPENDS:=$(GO_ARCH_DEPENDS) $(BPF_DEPENDS) \
	@KERNEL_DEBUG_INFO_BTF @KERNEL_BPF_STREAM_PARSER \
	+ca-bundle +kmod-sched-core +kmod-sched-bpf +kmod-veth
endef

define Package/daed/description
  daed bundles the dae transparent proxy, its GraphQL backend (dae-wing)
  and the web dashboard into one binary. dae splits traffic in the kernel
  with eBPF on tc hooks, so direct traffic never passes through a proxy
  process. It is an opt-in alternative to Passwall and refuses to start
  while Passwall is enabled. See docs/daed.md.
endef

define Package/daed/conffiles
/etc/config/daed
/etc/daed/wing.db
endef

define Package/daed-geoip
  $(call Package/daed/Default)
  TITLE:=GeoIP data for daed (from v2ray-geoip)
  DEPENDS:=+daed +v2ray-geoip
  PKGARCH:=all
endef

define Package/daed-geosite
  $(call Package/daed/Default)
  TITLE:=GeoSite data for daed (from v2ray-geosite)
  DEPENDS:=+daed +v2ray-geosite
  PKGARCH:=all
endef

# Go modules are fetched through the module proxy into the shared cache,
# as for the other Go packages in this tree.
DAED_GO_VARS= \
	$(GO_BIN_PATH) \
	GOOS="$(GO_OS)" \
	GOARCH="$(GO_ARCH)" \
	GOAMD64="$(GO_AMD64)" \
	CGO_ENABLED=0 \
	GOMODCACHE="$(GO_MOD_CACHE_DIR)" \
	GOFLAGS="-mod=mod -modcacherw" \
	GOCACHE="$(GO_BUILD_CACHE_DIR)" \
	GOENV=off \
	GOTOOLCHAIN=local

# Generators run on the host, so the target selection is cleared for them.
DAED_GO_HOST_VARS= \
	$(DAED_GO_VARS) \
	GOOS= GOARCH= GOAMD64=

DAED_BPF_VARS= \
	BPF_CLANG="$(CLANG)" \
	BPF_STRIP_FLAG="-strip=$(LLVM_STRIP)" \
	BPF_CFLAGS="-O2 -Wall -Werror -DMAX_MATCH_SET_LEN=$(DAED_MAX_MATCH_SET_LEN)" \
	BPF_TARGET="bpfel,bpfeb" \
	BPF_TRACE_TARGET="$(GO_ARCH)"

DAED_LDFLAGS:= \
	-s -w -buildid= \
	-X github.com/daeuniverse/dae-wing/db.AppName=$(PKG_NAME) \
	-X github.com/daeuniverse/dae-wing/db.AppVersion=$(PKG_VERSION) \
	-X github.com/daeuniverse/dae/common/consts.MaxMatchSetLen_=$(DAED_MAX_MATCH_SET_LEN)

define Build/Prepare
	$(PKG_UNPACK)
	rm -rf $(DAED_CORE_DIR)
	mkdir -p $(DAED_CORE_DIR)
	$(HOST_TAR) -C $(DAED_CORE_DIR) -xJf $(DL_DIR)/$(DAED_CORE_FILE)
	rm -rf $(PKG_BUILD_DIR)/webrender/web
	unzip -q -d $(PKG_BUILD_DIR)/webrender $(DL_DIR)/$(DAED_WEB_FILE)
	# Same compression step as dae-wing's "make bundle": keep whichever of the
	# plain and gzip-compressed file is smaller.
	find $(PKG_BUILD_DIR)/webrender/web -type f -size +4k \
		! -name '*.gz' ! -name '*.woff' ! -name '*.woff2' | \
	while read -r file; do \
		gzip -9 -n -k "$$$$file"; \
		if [ "$$$$(stat -c %s "$$$$file")" -lt "$$$$(stat -c %s "$$$$file.gz")" ]; then \
			rm -f "$$$$file.gz"; \
		else \
			rm -f "$$$$file"; \
		fi; \
	done
	$(Build/Patch)
endef

define Build/Configure
endef

define Build/Compile
	cd $(DAED_CORE_DIR) && \
		$(DAED_GO_HOST_VARS) $(DAED_BPF_VARS) go generate ./control/control.go && \
		$(DAED_GO_HOST_VARS) $(DAED_BPF_VARS) go generate ./trace/trace.go
	cd $(PKG_BUILD_DIR) && \
		$(DAED_GO_HOST_VARS) go generate ./... && \
		$(DAED_GO_VARS) go build -v -trimpath -buildvcs=false \
			-tags embedallowed,trace \
			-ldflags "$(DAED_LDFLAGS)" \
			-o $(PKG_BUILD_DIR)/daed .
endef

define Package/daed/install
	$(INSTALL_DIR) $(1)/usr/bin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/daed $(1)/usr/bin/daed
	$(INSTALL_DIR) $(1)/etc/config $(1)/etc/init.d
	$(INSTALL_CONF) ./files/daed.config $(1)/etc/config/daed
	$(INSTALL_BIN) ./files/daed.init $(1)/etc/init.d/daed
endef

# dae core searches $XDG_DATA_DIRS/dae, which defaults to /usr/share/dae.
define Package/daed-geoip/install
	$(INSTALL_DIR) $(1)/usr/share/dae
	$(LN) ../v2ray/geoip.dat $(1)/usr/share/dae/geoip.dat
endef

define Package/daed-geosite/install
	$(INSTALL_DIR) $(1)/usr/share/dae
	$(LN) ../v2ray/geosite.dat $(1)/usr/share/dae/geosite.dat
endef

$(eval $(call Download,dae-core))
$(eval $(call Download,daed-web))
$(eval $(call BuildPackage,daed))
$(eval $(call BuildPackage,daed-geoip))
$(eval $(call BuildPackage,daed-geosite))
