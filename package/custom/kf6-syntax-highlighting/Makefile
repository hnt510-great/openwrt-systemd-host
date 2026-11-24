include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-syntax-highlighting
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=syntax-highlighting-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=561d01001509299ad0578a02365e6bc714f2799724ac5980bc021c1ec2a44a67
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=Syntax Highlighting
KF6_DEPENDS:=+qt6base-core +qt6base-gui +qt6base-opengl +qt6quick
KF6_CMAKE_OPTIONS:=-DKSYNTAXHIGHLIGHTING_USE_GUI=ON

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
