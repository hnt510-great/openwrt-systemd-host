all: compile

compile: podman-luci-exec

podman-luci-exec: podman-luci-exec.c
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) -Wall -Wextra -o $@ $<

install: compile
	mkdir -p $(DESTDIR)/usr/libexec
	install -m 0755 podman-luci-exec $(DESTDIR)/usr/libexec/

clean:
	rm -f podman-luci-exec
