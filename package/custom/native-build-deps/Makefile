# SPDX-License-Identifier: GPL-2.0-only

include $(TOPDIR)/rules.mk

PKG_NAME:=native-build-deps
PKG_VERSION:=1
PKG_RELEASE:=2
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/native-build-deps
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=Common native application build dependencies
  EXTRA_DEPENDS:=native-libs-dev (>=1-r3)
  DEPENDS:=+native-libs-dev +gettext-tools +autoconf +automake +libtool-bin \
	+cmake-bin +bash +patch +diffutils +tar +gzip +xz \
	+flex +bison +python3 +python3-pip +python3-setuptools \
	+coreutils-env +coreutils-cat +coreutils-cp +coreutils-mv +coreutils-rm \
	+coreutils-mkdir +coreutils-rmdir +coreutils-dirname +coreutils-basename \
	+coreutils-install +coreutils-ln +coreutils-chmod +coreutils-touch \
	+coreutils-mktemp +coreutils-sort +coreutils-head +coreutils-tail \
	+coreutils-cut +coreutils-tr +coreutils-expr +coreutils-printf \
	+coreutils-readlink +coreutils-test +coreutils-true +coreutils-false \
	+coreutils-wc +coreutils-uname +coreutils-ls +coreutils-id +coreutils-date
endef

define Package/native-build-deps/description
  Installs target-native C/C++ library development files, GLib code generators,
  gettext translation tools, Autotools, CMake, parser generators and Python
  packaging tools. Includes the library dependencies needed to build Cockpit.
  Source checkouts can require additional project-specific build tools.
endef

define Build/Compile
endef

define Package/native-build-deps/install
	:
endef

$(eval $(call BuildPackage,native-build-deps))
