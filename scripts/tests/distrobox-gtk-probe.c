/* SPDX-License-Identifier: MIT */
#include <gtk/gtk.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static GtkWidget *entry;
static GtkWidget *result;
static GtkWidget *window;

static gboolean capture(gpointer data)
{
	const char *path = getenv("DISTROBOX_TEST_SCREENSHOT");
	cairo_surface_t *surface;
	cairo_t *context;
	cairo_status_t status;

	(void)data;
	if (!path)
		return G_SOURCE_REMOVE;
	surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32,
		gtk_widget_get_allocated_width(window),
		gtk_widget_get_allocated_height(window));
	context = cairo_create(surface);
	gtk_widget_draw(window, context);
	status = cairo_surface_write_to_png(surface, path);
	printf("DISTROBOX_GUI_CAPTURE=%s\n", cairo_status_to_string(status));
	fflush(stdout);
	cairo_destroy(context);
	cairo_surface_destroy(surface);
	return G_SOURCE_REMOVE;
}

static gboolean ready(GtkWidget *widget, cairo_t *context, gpointer data)
{
	static int reported;

	(void)widget;
	(void)context;
	(void)data;
	if (!reported) {
		puts("DISTROBOX_GUI_READY=1");
		fflush(stdout);
		reported = 1;
	}
	return FALSE;
}

static void verify(GtkWidget *widget, gpointer data)
{
	const char *text = gtk_entry_get_text(GTK_ENTRY(entry));
	const char *path = getenv("DISTROBOX_TEST_RESULT");
	FILE *file;

	(void)widget;
	(void)data;
	gtk_label_set_text(GTK_LABEL(result), text);
	printf("DISTROBOX_GUI_INPUT=%s\n", text);
	fflush(stdout);
	if (path && (file = fopen(path, "w"))) {
		fprintf(file, "%s\n", text);
		fclose(file);
	}
	g_timeout_add(100, capture, NULL);
}

static gboolean quit(gpointer data)
{
	(void)data;
	gtk_main_quit();
	return G_SOURCE_REMOVE;
}

int main(void)
{
	GtkWidget *box, *button;

	if (!getuid())
		return 1;
	gtk_init(NULL, NULL);
	printf("DISTROBOX_GUI_UID=%u\nDISTROBOX_GUI_BACKEND=%s\n",
	       (unsigned int)getuid(),
	       G_OBJECT_TYPE_NAME(gdk_display_get_default()));
	fflush(stdout);
	window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
	gtk_window_set_title(GTK_WINDOW(window), "Distrobox desktop integration");
	gtk_window_set_default_size(GTK_WINDOW(window), 460, 230);
	box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 20);
	gtk_container_set_border_width(GTK_CONTAINER(box), 24);
	gtk_container_add(GTK_CONTAINER(window), box);
	entry = gtk_entry_new();
	gtk_entry_set_placeholder_text(GTK_ENTRY(entry), "Type a marker and press Enter");
	gtk_box_pack_start(GTK_BOX(box), entry, TRUE, TRUE, 0);
	button = gtk_button_new_with_label("Verify Distrobox input");
	gtk_box_pack_start(GTK_BOX(box), button, TRUE, TRUE, 0);
	result = gtk_label_new("Waiting for keyboard or button input");
	gtk_box_pack_start(GTK_BOX(box), result, TRUE, TRUE, 0);
	g_signal_connect(entry, "activate", G_CALLBACK(verify), NULL);
	g_signal_connect(button, "clicked", G_CALLBACK(verify), NULL);
	g_signal_connect(window, "draw", G_CALLBACK(ready), NULL);
	g_signal_connect(window, "destroy", G_CALLBACK(gtk_main_quit), NULL);
	gtk_widget_show_all(window);
	gtk_widget_grab_focus(entry);
	g_timeout_add_seconds(180, quit, NULL);
	gtk_main();
	return 0;
}
