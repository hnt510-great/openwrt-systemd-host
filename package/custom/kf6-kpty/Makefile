include $(TOPDIR)/rules.mk

PKG_NAME:=kf6-kpty
PKG_VERSION:=6.32.0
PKG_RELEASE:=1
PKG_SOURCE:=kpty-$(PKG_VERSION).tar.xz
PKG_SOURCE_URL:=https://download.kde.org/stable/frameworks/6.32/
PKG_HASH:=ed8a6feee493a1b98930fb78d40e09a5a7983ec2f29ced0afc83ffbdb54f6152
PKG_LICENSE:=LGPL-2.1-or-later

KF6_TITLE:=PTY
KF6_DEPENDS:=+qt6base-core +kf6-kcoreaddons +kf6-ki18n +libutempter
# KPty records sessions through the setgid utempter helper at this path.
KF6_CMAKE_OPTIONS:=-DUTEMPTER_EXECUTABLE=/usr/lib/utempter/utempter

include $(INCLUDE_DIR)/kf6-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
