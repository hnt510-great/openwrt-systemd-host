/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <gtk/gtk.h>
#include <gio/gdesktopappinfo.h>
#include <string.h>
#include <unistd.h>

static GtkWidget *window, *search, *list, *message;
static char *query;

static gint compare_apps(gconstpointer a, gconstpointer b)
{
	return g_utf8_collate(g_app_info_get_display_name(G_APP_INFO((gpointer)a)),
			     g_app_info_get_display_name(G_APP_INFO((gpointer)b)));
}

static GList *applications(void)
{
	GList *all = g_app_info_get_all(), *result = NULL;

	for (GList *it = all; it; it = it->next) {
		GAppInfo *app = it->data;
		if (g_app_info_should_show(app))
			result = g_list_prepend(result, g_object_ref(app));
	}
	g_list_free_full(all, g_object_unref);
	return g_list_sort(result, compare_apps);
}

static gboolean launch(GAppInfo *app, GError **error)
{
	GAppLaunchContext *context;
	if (window)
		context = G_APP_LAUNCH_CONTEXT(gdk_display_get_app_launch_context(gtk_widget_get_display(window)));
	else
		context = g_app_launch_context_new();
	g_app_launch_context_unsetenv(context, "WAYLAND_SOCKET");
	gboolean success = g_app_info_launch(app, NULL, context, error);
	g_object_unref(context);
	return success;
}

static gboolean filter(GtkListBoxRow *row, gpointer unused)
{
	(void)unused;
	const char *text = g_object_get_data(G_OBJECT(row), "search-text");
	return !query || !*query || strstr(text, query) != NULL;
}

static void select_first(void)
{
	GList *rows = gtk_container_get_children(GTK_CONTAINER(list));
	GtkListBoxRow *first = NULL;
	for (GList *it = rows; it; it = it->next) {
		if (gtk_widget_get_child_visible(it->data)) {
			first = GTK_LIST_BOX_ROW(it->data);
			break;
		}
	}
	gtk_list_box_select_row(GTK_LIST_BOX(list), first);
	gtk_label_set_text(GTK_LABEL(message), first ? "" : "No applications found");
	g_list_free(rows);
}

static void changed(GtkEditable *entry, gpointer unused)
{
	(void)unused;
	g_free(query);
	query = g_utf8_casefold(gtk_entry_get_text(GTK_ENTRY(entry)), -1);
	gtk_list_box_invalidate_filter(GTK_LIST_BOX(list));
	select_first();
}

static void activate_row(GtkListBox *box, GtkListBoxRow *row, gpointer unused)
{
	(void)box;
	(void)unused;
	if (!row)
		return;
	GError *error = NULL;
	GAppInfo *app = g_object_get_data(G_OBJECT(row), "app");
	if (launch(app, &error))
		gtk_widget_hide(window);
	else {
		gtk_label_set_text(GTK_LABEL(message), error->message);
		g_clear_error(&error);
	}
}

static gboolean key_pressed(GtkWidget *widget, GdkEventKey *event, gpointer unused)
{
	(void)widget;
	(void)unused;
	if (event->keyval == GDK_KEY_Escape) {
		gtk_widget_hide(window);
		return TRUE;
	}
	if (event->keyval == GDK_KEY_Return || event->keyval == GDK_KEY_KP_Enter) {
		activate_row(GTK_LIST_BOX(list), gtk_list_box_get_selected_row(GTK_LIST_BOX(list)), NULL);
		return TRUE;
	}
	if (event->keyval == GDK_KEY_Down || event->keyval == GDK_KEY_Up) {
		GtkListBoxRow *selected = gtk_list_box_get_selected_row(GTK_LIST_BOX(list));
		int index = selected ? gtk_list_box_row_get_index(selected) : -1;
		int step = event->keyval == GDK_KEY_Down ? 1 : -1;
		GtkListBoxRow *next;
		while ((next = gtk_list_box_get_row_at_index(GTK_LIST_BOX(list), index += step))) {
			if (gtk_widget_get_child_visible(GTK_WIDGET(next))) {
				gtk_list_box_select_row(GTK_LIST_BOX(list), next);
				gtk_widget_grab_focus(GTK_WIDGET(next));
				gtk_widget_grab_focus(search);
				break;
			}
		}
		return TRUE;
	}
	return FALSE;
}

static void refresh(GAppInfoMonitor *monitor, gpointer unused)
{
	(void)monitor;
	(void)unused;
	if (!list)
		return;
	GList *rows = gtk_container_get_children(GTK_CONTAINER(list));
	for (GList *it = rows; it; it = it->next)
		gtk_widget_destroy(it->data);
	g_list_free(rows);
	GList *apps = applications();
	for (GList *it = apps; it; it = it->next) {
		GAppInfo *app = it->data;
		GtkWidget *row = gtk_list_box_row_new();
		GtkWidget *box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
		GIcon *icon = g_app_info_get_icon(app);
		GtkWidget *image = icon ? gtk_image_new_from_gicon(icon, GTK_ICON_SIZE_DIALOG) :
			gtk_image_new_from_icon_name("application-x-executable", GTK_ICON_SIZE_DIALOG);
		GtkWidget *label = gtk_label_new(g_app_info_get_display_name(app));
		gtk_label_set_xalign(GTK_LABEL(label), 0);
		gtk_label_set_ellipsize(GTK_LABEL(label), PANGO_ELLIPSIZE_END);
		gtk_container_set_border_width(GTK_CONTAINER(box), 8);
		gtk_box_pack_start(GTK_BOX(box), image, FALSE, FALSE, 0);
		gtk_box_pack_start(GTK_BOX(box), label, TRUE, TRUE, 0);
		gtk_container_add(GTK_CONTAINER(row), box);
		gtk_widget_set_tooltip_text(row, g_app_info_get_description(app));
		char *keywords = g_desktop_app_info_get_locale_string(G_DESKTOP_APP_INFO(app), "Keywords");
		char *generic = g_desktop_app_info_get_locale_string(G_DESKTOP_APP_INFO(app), "GenericName");
		char *text = g_strjoin(" ", g_app_info_get_display_name(app),
			generic ? generic : "", keywords ? keywords : "", NULL);
		g_object_set_data_full(G_OBJECT(row), "search-text", g_utf8_casefold(text, -1), g_free);
		g_object_set_data_full(G_OBJECT(row), "app", g_object_ref(app), g_object_unref);
		g_free(text);
		g_free(keywords);
		g_free(generic);
		gtk_container_add(GTK_CONTAINER(list), row);
		gtk_widget_show_all(row);
	}
	g_list_free_full(apps, g_object_unref);
	gtk_list_box_invalidate_filter(GTK_LIST_BOX(list));
	select_first();
}

static void activate(GtkApplication *application, gpointer unused)
{
	(void)unused;
	if (!window) {
		window = gtk_application_window_new(application);
		gtk_window_set_title(GTK_WINDOW(window), "Applications");
		gtk_window_set_default_size(GTK_WINDOW(window), 520, 560);
		gtk_window_set_icon_name(GTK_WINDOW(window), "desktop-applications");
		GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 8);
		gtk_container_set_border_width(GTK_CONTAINER(box), 12);
		search = gtk_search_entry_new();
		gtk_entry_set_placeholder_text(GTK_ENTRY(search), "Search applications");
		list = gtk_list_box_new();
		gtk_list_box_set_filter_func(GTK_LIST_BOX(list), filter, NULL, NULL);
		GtkWidget *scroll = gtk_scrolled_window_new(NULL, NULL);
		gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroll), GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
		gtk_container_add(GTK_CONTAINER(scroll), list);
		message = gtk_label_new("");
		gtk_label_set_line_wrap(GTK_LABEL(message), TRUE);
		gtk_box_pack_start(GTK_BOX(box), search, FALSE, FALSE, 0);
		gtk_box_pack_start(GTK_BOX(box), scroll, TRUE, TRUE, 0);
		gtk_box_pack_start(GTK_BOX(box), message, FALSE, FALSE, 0);
		gtk_container_add(GTK_CONTAINER(window), box);
		g_signal_connect(window, "delete-event", G_CALLBACK(gtk_widget_hide_on_delete), NULL);
		g_signal_connect(window, "key-press-event", G_CALLBACK(key_pressed), NULL);
		g_signal_connect(search, "search-changed", G_CALLBACK(changed), NULL);
		g_signal_connect(list, "row-activated", G_CALLBACK(activate_row), NULL);
		g_signal_connect(g_app_info_monitor_get(), "changed", G_CALLBACK(refresh), NULL);
	}
	gtk_entry_set_text(GTK_ENTRY(search), "");
	refresh(NULL, NULL);
	gtk_widget_show_all(window);
	gtk_widget_grab_focus(search);
	gtk_window_present(GTK_WINDOW(window));
}

int main(int argc, char **argv)
{
	/* The Weston panel can pass its VNC/RDP listeners to launched clients.
	 * Open our own Wayland connection and never retain those listeners. */
	closefrom(3);
	g_unsetenv("WAYLAND_SOCKET");
	if (argc == 2 && !strcmp(argv[1], "--list")) {
		GList *apps = applications();
		for (GList *it = apps; it; it = it->next)
			g_print("%s\t%s\n", g_app_info_get_id(it->data), g_app_info_get_display_name(it->data));
		g_list_free_full(apps, g_object_unref);
		return 0;
	}
	if (argc == 3 && !strcmp(argv[1], "--launch")) {
		GDesktopAppInfo *app = g_desktop_app_info_new(argv[2]);
		GError *error = NULL;
		if (!app || !g_app_info_should_show(G_APP_INFO(app))) {
			g_printerr("Application is unavailable: %s\n", argv[2]);
			g_clear_object(&app);
			return 1;
		}
		gboolean success = launch(G_APP_INFO(app), &error);
		if (error) {
			g_printerr("%s\n", error->message);
			g_clear_error(&error);
		}
		g_object_unref(app);
		return success ? 0 : 1;
	}
	GtkApplication *application = gtk_application_new("org.openwrt.DesktopApplications", G_APPLICATION_DEFAULT_FLAGS);
	g_signal_connect(application, "activate", G_CALLBACK(activate), NULL);
	int status = g_application_run(G_APPLICATION(application), argc, argv);
	g_object_unref(application);
	g_free(query);
	return status;
}
