// SPDX-License-Identifier: MIT
/* Run as the desktop user while an RDP client is connected, then disconnect it.
 * Requires wayland-client and generated tablet-unstable-v2 client protocol code.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wayland-client.h>
#include "tablet-unstable-v2-client-protocol.h"

struct seat {
	uint32_t id, version;
	struct wl_seat *proxy;
	struct zwp_tablet_seat_v2 *tablet;
	struct seat *next;
	int remote;
};
static struct seat *seats;
static struct zwp_tablet_manager_v2 *manager;
static int retired;
static int late_bind;

static void capabilities(void *data, struct wl_seat *seat, uint32_t caps)
{
	(void)data; (void)seat; (void)caps;
}
static void name(void *data, struct wl_seat *proxy, const char *value)
{
	struct seat *seat = data;
	(void)proxy;
	seat->remote = strncmp(value, "RDP ", 4) == 0;
	if (seat->remote) {
		puts("RDP seat bound; disconnect the RDP client now");
		fflush(stdout);
	}
}
static const struct wl_seat_listener seat_listener = { capabilities, name };
static void global(void *data, struct wl_registry *registry, uint32_t id,
		   const char *interface, uint32_t version)
{
	struct seat *seat;
	(void)data;
	if (!strcmp(interface, "zwp_tablet_manager_v2"))
		manager = wl_registry_bind(registry, id, &zwp_tablet_manager_v2_interface, 1);
	if (strcmp(interface, "wl_seat"))
		return;
	seat = calloc(1, sizeof(*seat));
	if (!seat)
		exit(1);
	seat->id = id;
	seat->version = version < 5 ? version : 5;
	seat->next = seats;
	seats = seat;
	if (late_bind)
		return;
	seat->proxy = wl_registry_bind(registry, id, &wl_seat_interface, version < 5 ? version : 5);
	wl_seat_add_listener(seat->proxy, &seat_listener, seat);
}
static void removed(void *data, struct wl_registry *registry, uint32_t id)
{
	struct seat *seat;
	(void)data; (void)registry;
	for (seat = seats; seat; seat = seat->next) {
		if (seat->id != id || (!late_bind && !seat->remote))
			continue;
		if (late_bind) {
			seat->proxy = wl_registry_bind(registry, id, &wl_seat_interface,
						      seat->version);
			wl_pointer_destroy(wl_seat_get_pointer(seat->proxy));
			wl_keyboard_destroy(wl_seat_get_keyboard(seat->proxy));
			wl_touch_destroy(wl_seat_get_touch(seat->proxy));
			retired = 1;
			continue;
		}
		/* Exercise both existing resource destruction and a late request. */
		if (seat->tablet)
			zwp_tablet_seat_v2_destroy(seat->tablet);
		seat->tablet = zwp_tablet_manager_v2_get_tablet_seat(manager, seat->proxy);
		retired = 1;
	}
}
static const struct wl_registry_listener registry_listener = { global, removed };
int main(int argc, char **argv)
{
	struct wl_display *display = wl_display_connect(NULL);
	struct wl_registry *registry;
	struct seat *seat;

	if (argc > 1)
		late_bind = !strcmp(argv[1], "--late-bind");
	if (!display) {
		perror("wl_display_connect");
		return 1;
	}
	registry = wl_display_get_registry(display);
	wl_registry_add_listener(registry, &registry_listener, NULL);
	if (wl_display_roundtrip(display) < 0 || (!late_bind && !manager)) {
		fprintf(stderr, "registry roundtrip failed or tablet manager missing\n");
		return 1;
	}
	if (wl_display_roundtrip(display) < 0)
		return 1;
	if (late_bind) {
		puts("Ready; connect and disconnect a VNC client now");
		fflush(stdout);
	} else {
		for (seat = seats; seat; seat = seat->next)
			seat->tablet = zwp_tablet_manager_v2_get_tablet_seat(manager, seat->proxy);
	}
	while (!retired)
		if (wl_display_dispatch(display) < 0)
			return 1;
	if (wl_display_roundtrip(display) < 0)
		return 1;
	puts(late_bind ? "PASS: removed seat global accepts an inert bind" :
	     "PASS: removed RDP seat accepts an inert tablet request");
	wl_display_disconnect(display);
	return 0;
}
