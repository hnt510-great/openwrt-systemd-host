ARCH:=x86_64
BOARDNAME:=x86_64

# Keep other x86 subtargets on their existing LTS kernel.
KERNEL_PATCHVER:=7.3

define Target/Description
        Build images for 64 bit systems including virtualized guests.
endef
