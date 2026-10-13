/* SPDX-License-Identifier: MIT */
#include <gtk/gtk.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/vfs.h>
#include <unistd.h>

static GtkWidget *result;

static void calculate(GtkButton *button, gpointer data)
{
	GtkClipboard *clipboard = gtk_clipboard_get(GDK_SELECTION_CLIPBOARD);
	const char *marker = getenv("APPIMAGE_TEST_RESULT");
	FILE *file;

	(void)button;
	(void)data;
	gtk_label_set_text(GTK_LABEL(result), "7 + 5 = 12");
	gtk_clipboard_set_text(clipboard, "appimage-probe-12", -1);
	puts("APPIMAGE_PROBE_RESULT=12");
	fflush(stdout);
	if (marker && (file = fopen(marker, "w"))) {
		fputs("12\n", file);
		fclose(file);
	}
}

static gboolean quit(gpointer data)
{
	(void)data;
	gtk_main_quit();
	return G_SOURCE_REMOVE;
}

int main(int argc, char **argv)
{
	const char *appdir = getenv("APPDIR");
	const char *image = getenv("APPIMAGE");
	const char *timeout = getenv("APPIMAGE_TEST_TIMEOUT");
	struct statfs fs;
	GtkWidget *window, *box, *button;
	int i;

	if (!getuid()) {
		fputs("appimage-probe: run as an ordinary user\n", stderr);
		return 1;
	}
	printf("APPIMAGE_PROBE_UID=%u\n", (unsigned int)getuid());
	printf("APPIMAGE_PROBE_APPDIR=%s\n", appdir ? appdir : "");
	printf("APPIMAGE_PROBE_IMAGE=%s\n", image ? image : "");
	if (appdir && !statfs(appdir, &fs))
		printf("APPIMAGE_PROBE_FUSE=%d\n", fs.f_type == 0x65735546);
	if (argc > 1 && !strcmp(argv[1], "--cli")) {
		for (i = 2; i < argc; i++)
			printf("APPIMAGE_PROBE_ARGUMENT=%s\n", argv[i]);
		return appdir && image ? 0 : 1;
	}
	gtk_init(NULL, NULL);
	if (argc > 1 && !strcmp(argv[1], "--clipboard")) {
		gchar *text = gtk_clipboard_wait_for_text(gtk_clipboard_get(GDK_SELECTION_CLIPBOARD));
		printf("APPIMAGE_PROBE_CLIPBOARD=%s\n", text ? text : "");
		i = text && !strcmp(text, "appimage-probe-12") ? 0 : 1;
		g_free(text);
		return i;
	}
	printf("APPIMAGE_PROBE_BACKEND=%s\n",
	       G_OBJECT_TYPE_NAME(gdk_display_get_default()));
	fflush(stdout);
	window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
	gtk_window_set_title(GTK_WINDOW(window), "AppImage input and clipboard probe");
	gtk_window_set_default_size(GTK_WINDOW(window), 420, 220);
	box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 24);
	gtk_container_set_border_width(GTK_CONTAINER(box), 24);
	gtk_container_add(GTK_CONTAINER(window), box);
	result = gtk_label_new("Press Calculate, or Space when the button is focused");
	gtk_box_pack_start(GTK_BOX(box), result, TRUE, TRUE, 0);
	button = gtk_button_new_with_label("Calculate 7 + 5");
	gtk_box_pack_start(GTK_BOX(box), button, TRUE, TRUE, 0);
	g_signal_connect(button, "clicked", G_CALLBACK(calculate), NULL);
	g_signal_connect(window, "destroy", G_CALLBACK(gtk_main_quit), NULL);
	gtk_widget_show_all(window);
	gtk_widget_grab_focus(button);
	g_timeout_add_seconds(timeout ? (guint)atoi(timeout) : 120, quit, NULL);
	gtk_main();
	return 0;
}
