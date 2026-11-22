include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-breeze-icons
PKG_VERSION:=6.20.0
PKG_RELEASE:=2
PKG_SOURCE:=breeze-icons-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.20/
PKG_HASH:=0a47b28a04a086ccb5b4afb51d6677180006819d0d9302524721689bfa4ad13c
PKG_LICENSE:=LGPL-3.0-only
PKG_LICENSE_FILES:=COPYING.LGPL-3

KF6_TITLE:=Breeze Icons
KF6_DEPENDS:=+qt6base-core +qt6base-gui
# 24x24 icon generation needs the host's Python lxml module, which is not
# part of the build prerequisite set. Scalable and symbolic icons are
# installed unchanged; KIconLoader scales the SVGs at runtime.
KF6_CMAKE_OPTIONS:=-DWITH_ICON_GENERATION=OFF

# Breeze Icons rejects an in-source build.
CMAKE_BINARY_SUBDIR:=build

include $(INCLUDE_DIR)/kf6-package.mk

# Copy the theme and make Breeze the default icon theme for KDE applications
# instead of relying on Qt's platform theme (GNOME would select Adwaita).
define Package/kf6-breeze-icons/install
	[ ! -d $(PKG_INSTALL_DIR)/usr ] || $(CP) $(PKG_INSTALL_DIR)/usr $(1)/
	[ ! -d $(PKG_INSTALL_DIR)/etc ] || $(CP) $(PKG_INSTALL_DIR)/etc $(1)/
	$(RM) -r $(1)/usr/include $(1)/usr/lib/cmake $(1)/usr/lib/pkgconfig \
		$(1)/usr/share/doc $(1)/usr/share/man
	find $(1) -type f \( -name '*.a' -o -name '*.la' \) -delete
	$(INSTALL_DIR) $(1)/etc/xdg
	$(INSTALL_DATA) ./files/kdeglobals $(1)/etc/xdg/kdeglobals
	for theme in breeze breeze-dark; do \
		for d in actions/16 actions/22; do \
			ln -sf view-split-left-right.svg "$(1)/usr/share/icons/$$$${theme}/$$$${d}/view-split-auto.svg"; \
		done; \
		for d in apps/16 apps/22 apps/32 apps/48 apps/64; do \
			[ ! -f "$(1)/usr/share/icons/$$$${theme}/$$$${d}/accessories-text-editor.svg" ] || \
				ln -sf accessories-text-editor.svg "$(1)/usr/share/icons/$$$${theme}/$$$${d}/org.gnome.gedit.svg"; \
		done; \
	done
	$(SED) 's/^Inherits=hicolor.*/Inherits=hicolor,Adwaita/' $(1)/usr/share/icons/breeze/index.theme
	$(SED) 's/^Inherits=hicolor.*/Inherits=hicolor,Adwaita/' $(1)/usr/share/icons/breeze-dark/index.theme
endef

define Package/kf6-breeze-icons/conffiles
/etc/xdg/kdeglobals
endef

$(eval $(call BuildPackage,$(PKG_NAME)))
