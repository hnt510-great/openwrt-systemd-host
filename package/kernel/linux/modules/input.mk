#
# Copyright (C) 2006-2013 OpenWrt.org
#
# This is free software, licensed under the GNU General Public License v2.
# See /LICENSE for more information.
#

INPUT_MODULES_MENU:=Input modules

define KernelPackage/hid
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=HID Devices
  DEPENDS:=+kmod-input-core +PACKAGE_input-support:kmod-input-evdev
  KCONFIG:=CONFIG_HID CONFIG_HID_SUPPORT=y CONFIG_HIDRAW=y CONFIG_HID_BATTERY_STRENGTH=y
  FILES:=$(LINUX_DIR)/drivers/hid/hid.ko
  AUTOLOAD:=$(call AutoLoad,61,hid)
endef

define KernelPackage/hid/description
 Kernel modules for HID devices
endef

$(eval $(call KernelPackage,hid))

define KernelPackage/hid-generic
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Generic HID device support
  DEPENDS:=+kmod-hid
  KCONFIG:=CONFIG_HID_GENERIC
  FILES:=$(LINUX_DIR)/drivers/hid/hid-generic.ko
  AUTOLOAD:=$(call AutoProbe,hid-generic)
endef

define KernelPackage/hid/description
 Kernel modules for generic HID device (e.g. keyboards and mice) support
endef

$(eval $(call KernelPackage,hid-generic))


define KernelPackage/uhid
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=User-space HID device support
  DEPENDS:=+kmod-hid
  KCONFIG:=CONFIG_UHID
  FILES:=$(LINUX_DIR)/drivers/hid/uhid.ko
  AUTOLOAD:=$(call AutoProbe,uhid)
endef

define KernelPackage/uhid/description
 Kernel module that lets user space create HID devices, used by BlueZ
 for Bluetooth Low Energy HID devices
endef

$(eval $(call KernelPackage,uhid))


define KernelPackage/hid-alps
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Alps HID device support
  DEPENDS:=+kmod-hid
  KCONFIG:=CONFIG_HID_ALPS
  FILES:=$(LINUX_DIR)/drivers/hid/hid-alps.ko
  AUTOLOAD:=$(call AutoProbe,hid-alps)
endef

define KernelPackage/hid-alps/description
 Support for Alps I2C HID touchpads and StickPointer.
endef

$(eval $(call KernelPackage,hid-alps))

define KernelPackage/hid-multitouch
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=HID multitouch panel support
  DEPENDS:=+kmod-hid
  KCONFIG:=CONFIG_HID_MULTITOUCH
  FILES:=$(LINUX_DIR)/drivers/hid/hid-multitouch.ko
  AUTOLOAD:=$(call AutoProbe,hid-multitouch)
endef

define KernelPackage/hid-multitouch/description
 Support for HID multitouch touchscreens and touchpads that report
 more than one contact, on USB, I2C or Bluetooth
endef

$(eval $(call KernelPackage,hid-multitouch))

define KernelPackage/input-ff-memless
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Memoryless force-feedback input support
  DEPENDS:=+kmod-input-core
  KCONFIG:=CONFIG_INPUT_FF_MEMLESS
  FILES:=$(LINUX_DIR)/drivers/input/ff-memless.ko
  AUTOLOAD:=$(call AutoProbe,ff-memless)
endef

define KernelPackage/input-ff-memless/description
 Support for memoryless force-feedback (rumble) input devices.
endef

$(eval $(call KernelPackage,input-ff-memless))

define KernelPackage/hid-logitech
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Logitech HID, Unifying/Bolt DJ and HID++ support
  DEPENDS:=+kmod-hid +kmod-input-ff-memless
  KCONFIG:= \
	CONFIG_HID_LOGITECH \
	CONFIG_HID_LOGITECH_DJ \
	CONFIG_HID_LOGITECH_HIDPP \
	CONFIG_LOGITECH_FF=y \
	CONFIG_LOGIRUMBLEPAD2_FF=y \
	CONFIG_LOGIG940_FF=y \
	CONFIG_LOGIWHEELS_FF=y
  FILES:= \
	$(LINUX_DIR)/drivers/hid/hid-logitech.ko \
	$(LINUX_DIR)/drivers/hid/hid-lg-g15.ko \
	$(LINUX_DIR)/drivers/hid/hid-logitech-dj.ko \
	$(LINUX_DIR)/drivers/hid/hid-logitech-hidpp.ko
  AUTOLOAD:=$(call AutoProbe,hid-logitech hid-lg-g15 hid-logitech-dj hid-logitech-hidpp)
endef

define KernelPackage/hid-logitech/description
 Support for Logitech HID keyboards, mice, Unifying/Bolt wireless receivers
 (DJ/HID++) and force-feedback peripherals.
endef

$(eval $(call KernelPackage,hid-logitech))

define KernelPackage/hid-playstation
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Sony PlayStation HID controller support
  DEPENDS:=+kmod-hid +kmod-input-ff-memless
  KCONFIG:= \
	CONFIG_HID_PLAYSTATION \
	CONFIG_PLAYSTATION_FF=y
  FILES:=$(LINUX_DIR)/drivers/hid/hid-playstation.ko
  AUTOLOAD:=$(call AutoProbe,hid-playstation)
endef

define KernelPackage/hid-playstation/description
 Support for Sony PlayStation DualShock 4 and DualSense HID controllers.
endef

$(eval $(call KernelPackage,hid-playstation))

define KernelPackage/hid-nintendo
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Nintendo Switch HID controller support
  DEPENDS:=+kmod-hid +kmod-input-ff-memless
  KCONFIG:= \
	CONFIG_HID_NINTENDO \
	CONFIG_NINTENDO_FF=y
  FILES:=$(LINUX_DIR)/drivers/hid/hid-nintendo.ko
  AUTOLOAD:=$(call AutoProbe,hid-nintendo)
endef

define KernelPackage/hid-nintendo/description
 Support for Nintendo Joy-Con, NSO and Pro Controller HID gamepads.
endef

$(eval $(call KernelPackage,hid-nintendo))

define KernelPackage/input-xpad
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Xbox USB gamepad support
  DEPENDS:=+kmod-input-core +kmod-input-ff-memless +kmod-usb-core
  KCONFIG:= \
	CONFIG_INPUT_JOYSTICK=y \
	CONFIG_JOYSTICK_XPAD \
	CONFIG_JOYSTICK_XPAD_FF=y \
	CONFIG_JOYSTICK_XPAD_LEDS=y \
	CONFIG_JOYSTICK_ANALOG=n \
	CONFIG_JOYSTICK_A3D=n \
	CONFIG_JOYSTICK_ADI=n \
	CONFIG_JOYSTICK_COBRA=n \
	CONFIG_JOYSTICK_GF2K=n \
	CONFIG_JOYSTICK_GRIP=n \
	CONFIG_JOYSTICK_GRIP_MP=n \
	CONFIG_JOYSTICK_GUILLEMOT=n \
	CONFIG_JOYSTICK_INTERACT=n \
	CONFIG_JOYSTICK_SIDEWINDER=n \
	CONFIG_JOYSTICK_TMDC=n \
	CONFIG_JOYSTICK_IFORCE=n \
	CONFIG_JOYSTICK_WARRIOR=n \
	CONFIG_JOYSTICK_MAGELLAN=n \
	CONFIG_JOYSTICK_SPACEORB=n \
	CONFIG_JOYSTICK_SPACEBALL=n \
	CONFIG_JOYSTICK_STINGER=n \
	CONFIG_JOYSTICK_TWIDJOY=n \
	CONFIG_JOYSTICK_ZHENHUA=n \
	CONFIG_JOYSTICK_AS5011=n \
	CONFIG_JOYSTICK_JOYDUMP=n \
	CONFIG_JOYSTICK_PXRC=n \
	CONFIG_JOYSTICK_QWIIC=n \
	CONFIG_JOYSTICK_FSIA6B=n \
	CONFIG_JOYSTICK_SENSEHAT=n \
	CONFIG_JOYSTICK_SEESAW=n
  FILES:=$(LINUX_DIR)/drivers/input/joystick/xpad.ko
  AUTOLOAD:=$(call AutoProbe,xpad)
endef

define KernelPackage/input-xpad/description
 Support for Microsoft Xbox and compatible USB gamepads with rumble and LEDs.
endef

$(eval $(call KernelPackage,input-xpad))

define KernelPackage/input-adc-keys
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=ADC Ladder Buttons support
  DEPENDS:=+kmod-input-core +kmod-iio-core
  KCONFIG:= \
	CONFIG_KEYBOARD_ADC \
	CONFIG_INPUT_KEYBOARD=y
  FILES:=$(LINUX_DIR)/drivers/input/keyboard/adc-keys.ko
  AUTOLOAD:=$(call AutoProbe,adc-keys,1)
endef

define KernelPackage/input-adc-keys/description
 Buttons/keys input driver for resistor ladder connected on ADC
endef

$(eval $(call KernelPackage,input-adc-keys))

define KernelPackage/input-core
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Input device core
  KCONFIG:=CONFIG_INPUT
  FILES:=$(LINUX_DIR)/drivers/input/input-core.ko
endef

define KernelPackage/input-core/description
 Kernel modules for support of input device
endef

$(eval $(call KernelPackage,input-core))


define KernelPackage/input-evdev
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Input event device
  DEPENDS:=input-support +kmod-input-core
  KCONFIG:=CONFIG_INPUT_EVDEV
  FILES:=$(LINUX_DIR)/drivers/input/evdev.ko
  AUTOLOAD:=$(call AutoLoad,60,evdev)
endef

define KernelPackage/input-evdev/description
 Kernel modules for support of input device events
endef

$(eval $(call KernelPackage,input-evdev))


define KernelPackage/input-gpio-keys
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=GPIO key support
  DEPENDS:= @GPIO_SUPPORT +kmod-input-core
  KCONFIG:= \
	CONFIG_KEYBOARD_GPIO \
	CONFIG_INPUT_KEYBOARD=y
  FILES:=$(LINUX_DIR)/drivers/input/keyboard/gpio_keys.ko
  AUTOLOAD:=$(call AutoProbe,gpio_keys,1)
endef

define KernelPackage/input-gpio-keys/description
 This driver implements support for buttons connected
 to GPIO pins of various CPUs (and some other chips).

 See also gpio-button-hotplug which is an alternative, lower overhead
 implementation that generates uevents instead of kernel input events.
endef

$(eval $(call KernelPackage,input-gpio-keys))


define KernelPackage/input-gpio-keys-polled
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Polled GPIO key support
  DEPENDS:=@GPIO_SUPPORT +kmod-input-core
  KCONFIG:= \
	CONFIG_KEYBOARD_GPIO_POLLED \
	CONFIG_INPUT_KEYBOARD=y
  FILES:=$(LINUX_DIR)/drivers/input/keyboard/gpio_keys_polled.ko
  AUTOLOAD:=$(call AutoProbe,gpio_keys_polled,1)
endef

define KernelPackage/input-gpio-keys-polled/description
 Kernel module for support polled GPIO keys input device

 See also gpio-button-hotplug which is an alternative, lower overhead
 implementation that generates uevents instead of kernel input events.
endef

$(eval $(call KernelPackage,input-gpio-keys-polled))


define KernelPackage/input-gpio-encoder
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=GPIO rotary encoder
  DEPENDS:=@GPIO_SUPPORT +kmod-input-core
  KCONFIG:=CONFIG_INPUT_GPIO_ROTARY_ENCODER
  FILES:=$(LINUX_DIR)/drivers/input/misc/rotary_encoder.ko
  AUTOLOAD:=$(call AutoProbe,rotary_encoder)
endef

define KernelPackage/input-gpio-encoder/description
 Kernel module to use rotary encoders connected to GPIO pins
endef

$(eval $(call KernelPackage,input-gpio-encoder))


define KernelPackage/input-matrix-keypad
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=GPIO matrix keypad support
  DEPENDS:= @GPIO_SUPPORT +kmod-input-core +kmod-input-matrixkmap
  KCONFIG:= \
	CONFIG_KEYBOARD_MATRIX \
	CONFIG_INPUT_KEYBOARD=y
  FILES:=$(LINUX_DIR)/drivers/input/keyboard/matrix_keypad.ko
  AUTOLOAD:=$(call AutoProbe,matrix_keypad,1)
endef

define KernelPackage/input-matrix-keypad/description
 Enable support for GPIO driven matrix keypad.
endef

$(eval $(call KernelPackage,input-matrix-keypad))

define KernelPackage/input-joydev
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Joystick device support
  DEPENDS:=input-support +kmod-input-core
  KCONFIG:=CONFIG_INPUT_JOYDEV
  FILES:=$(LINUX_DIR)/drivers/input/joydev.ko
  AUTOLOAD:=$(call AutoProbe,joydev)
endef

define KernelPackage/input-joydev/description
 Kernel module for joystick support
endef

$(eval $(call KernelPackage,input-joydev))


define KernelPackage/input-matrixkmap
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Input matrix devices support
  DEPENDS:=+kmod-input-core
  KCONFIG:=CONFIG_INPUT_MATRIXKMAP
  FILES:=$(LINUX_DIR)/drivers/input/matrix-keymap.ko
  AUTOLOAD:=$(call AutoProbe,matrix-keymap)
endef

define KernelPackage/input-matrixkmap/description
 Kernel module support for input matrix devices
endef

$(eval $(call KernelPackage,input-matrixkmap))


define KernelPackage/input-touchscreen-ads7846
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=ADS7846/TSC2046/AD7873 and AD(S)7843 based touchscreens
  DEPENDS:=+kmod-hwmon-core +kmod-input-core +kmod-spi-bitbang
  KCONFIG:= \
	CONFIG_INPUT_TOUCHSCREEN=y \
	CONFIG_TOUCHSCREEN_ADS7846
  FILES:=$(LINUX_DIR)/drivers/input/touchscreen/ads7846.ko
  AUTOLOAD:=$(call AutoProbe,ads7846)
endef

define KernelPackage/input-touchscreen-ads7846/description
  Kernel module for ADS7846/TSC2046/AD7873 and AD(S)7843 based touchscreens
endef

$(eval $(call KernelPackage,input-touchscreen-ads7846))


define KernelPackage/input-touchscreen-edt-ft5x06
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=EDT FT5x06 and Focaltech FT6236 based touchscreens
  DEPENDS:=+kmod-i2c-core +kmod-input-core +kmod-regmap-i2c
  KCONFIG:= \
	CONFIG_INPUT_TOUCHSCREEN=y \
	CONFIG_TOUCHSCREEN_EDT_FT5X06
  FILES:=$(LINUX_DIR)/drivers/input/touchscreen/edt-ft5x06.ko
  AUTOLOAD:=$(call AutoProbe,edt-ft5x06)
endef

define KernelPackage/input-touchscreen-edt-ft5x06/description
  Kernel module for EDT FT5206, FT5306, FT5406, FT5506, Evervision FT5726 \
  and Focaltech FT6236 based touchscreens
endef

$(eval $(call KernelPackage,input-touchscreen-edt-ft5x06))


define KernelPackage/input-touchscreen-hynitron-cst816x
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Hynitron CST816X touchscreen
  DEPENDS:=+kmod-i2c-core +kmod-input-core
  KCONFIG:= \
	CONFIG_INPUT_TOUCHSCREEN=y \
	CONFIG_TOUCHSCREEN_HYNITRON_CST816X
  FILES:=$(LINUX_DIR)/drivers/input/touchscreen/hynitron-cst816x.ko
  AUTOLOAD:=$(call AutoProbe,hynitron-cst816x)
endef

define KernelPackage/input-touchscreen-hynitron-cst816x/description
  Kernel module for Hynitron CST816X touchscreen controller
  used for 240×240 1.28-inch Round LCD Display Module.
endef

$(eval $(call KernelPackage,input-touchscreen-hynitron-cst816x))


define KernelPackage/keyboard-imx
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=IMX keypad support
  DEPENDS:=@(TARGET_mxs||TARGET_imx) +kmod-input-matrixkmap
  KCONFIG:= \
	CONFIG_KEYBOARD_IMX \
	CONFIG_INPUT_KEYBOARD=y
  FILES:=$(LINUX_DIR)/drivers/input/keyboard/imx_keypad.ko
  AUTOLOAD:=$(call AutoProbe,imx_keypad)
endef

define KernelPackage/keyboard-imx/description
 Enable support for IMX keypad port.
endef

$(eval $(call KernelPackage,keyboard-imx))


define KernelPackage/input-uinput
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=user input module
  DEPENDS:=+kmod-input-core
  KCONFIG:= \
	CONFIG_INPUT_MISC=y \
	CONFIG_INPUT_UINPUT
  FILES:=$(LINUX_DIR)/drivers/input/misc/uinput.ko
  AUTOLOAD:=$(call AutoProbe,uinput)
endef

define KernelPackage/input-uinput/description
  user input modules needed for bluez
endef

$(eval $(call KernelPackage,input-uinput))


define KernelPackage/input-mouse-ps2
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=PS/2 mouse support
  DEPENDS:=+kmod-i2c-core +kmod-input-core +kmod-input-serio-libps2
  KCONFIG:= \
	CONFIG_INPUT_MOUSE=y \
	CONFIG_MOUSE_PS2 \
	CONFIG_MOUSE_PS2_ALPS=y \
	CONFIG_MOUSE_PS2_BYD=y \
	CONFIG_MOUSE_PS2_LOGIPS2PP=y \
	CONFIG_MOUSE_PS2_SYNAPTICS=y \
	CONFIG_MOUSE_PS2_SYNAPTICS_SMBUS=y \
	CONFIG_MOUSE_PS2_CYPRESS=y \
	CONFIG_MOUSE_PS2_LIFEBOOK=y \
	CONFIG_MOUSE_PS2_TRACKPOINT=y \
	CONFIG_MOUSE_PS2_ELANTECH=y \
	CONFIG_MOUSE_PS2_ELANTECH_SMBUS=y \
	CONFIG_MOUSE_PS2_SENTELIC=y \
	CONFIG_MOUSE_PS2_TOUCHKIT=y \
	CONFIG_MOUSE_PS2_OLPC=y \
	CONFIG_MOUSE_PS2_FOCALTECH=y \
	CONFIG_MOUSE_PS2_VMMOUSE=y
  FILES:=$(LINUX_DIR)/drivers/input/mouse/psmouse.ko
  AUTOLOAD:=$(call AutoProbe,psmouse)
endef

define KernelPackage/input-mouse-ps2/description
  Support for standard 2 or 3-button PS/2 mouse, as well as PS/2
  mice with wheels and extra buttons, Microsoft, Logitech or Genius
  compatible, and many touchpads as well.
endef

$(eval $(call KernelPackage,input-mouse-ps2))


define KernelPackage/input-serio
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Serial I/O support
  KCONFIG:= CONFIG_SERIO
  FILES:=$(LINUX_DIR)/drivers/input/serio/serio.ko
  AUTOLOAD:=$(call AutoProbe,serio,1)
endef

define KernelPackage/input-serio/description
 Kernel module to support input device that uses serial I/O to
 communicate with the system
endef

$(eval $(call KernelPackage,input-serio))


define KernelPackage/input-serio-libps2
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=PS/2 Serial I/O support
  DEPENDS:=+kmod-input-serio
  KCONFIG:= CONFIG_SERIO_LIBPS2
  FILES:=$(LINUX_DIR)/drivers/input/serio/libps2.ko
  AUTOLOAD:=$(call AutoProbe,libps2,1)
endef

define KernelPackage/input-serio-libps2/description
 Kernel module to support devices connected to a PS/2 port, such
 as PS/2 mouse or standard AT keyboard.
endef

$(eval $(call KernelPackage,input-serio-libps2))

define KernelPackage/rc-core
  SUBMENU:=$(INPUT_MODULES_MENU)
  TITLE:=Remote Controller support
  KCONFIG:= \
	CONFIG_RC_DEVICES=y \
	CONFIG_RC_CORE
  FILES:=$(LINUX_DIR)/drivers/media/rc/rc-core.ko
  AUTOLOAD:=$(call AutoProbe,rc-core)
  DEPENDS:=+kmod-input-core
endef

define KernelPackage/rc-core/description
 Enable support for Remote Controllers on Linux. This is
 needed in order to support several video capture adapters,
 standalone IR receivers/transmitters, and RF receivers.

 Enable this option if you have a video capture board even
 if you don't need IR, as otherwise, you may not be able to
 compile the driver for your adapter.
endef

$(eval $(call KernelPackage,rc-core))
