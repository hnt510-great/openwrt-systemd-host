include $(TOPDIR)/rules.mk

PKG_NAME:=wl-clipboard
PKG_VERSION:=2.3.0
PKG_RELEASE:=1
PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/bugaevc/wl-clipboard/tar.gz/refs/tags/
PKG_SOURCE_URL_FILE:=v$(PKG_VERSION)
PKG_HASH:=b4dc560973f0cd74e02f817ffa2fd44ba645a4f1ea94b7b9614dacc9f895f402
PKG_LICENSE:=GPL-3.0-or-later
PKG_LICENSE_FILES:=COPYING
PKG_BUILD_DEPENDS:=wayland/host wayland-protocols
GNOME_TITLE:=Wayland copy and paste command line utilities
GNOME_DEPENDS:=+libwayland
GNOME_MESON_ARGS:=-Dzshcompletiondir=no -Dfishcompletiondir=no

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
