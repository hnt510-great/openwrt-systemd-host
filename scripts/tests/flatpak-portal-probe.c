/* Run in a disposable Flatpak with only the Wayland socket permission.
 * The dialog must grant access via the document portal; do not grant host/home.
 */
#include <gtk/gtk.h>
#include <stdio.h>

int main(int argc, char **argv)
{
	GtkWidget *window;
	GtkFileChooserNative *chooser;
	GError *error = NULL;
	gchar *filename;
	gint response;

	gtk_init(&argc, &argv);
	if (argc != 2) {
		g_printerr("Expected an unauthorized host-file path\n");
		return 2;
	}
	if (g_file_test(argv[1], G_FILE_TEST_EXISTS)) {
		g_printerr("Unauthorized host file was exposed before file selection\n");
		return 3;
	}
	window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
	gtk_window_set_title(GTK_WINDOW(window), "Flatpak portal validation");
	gtk_widget_show(window);
	chooser = gtk_file_chooser_native_new("Save the authorized test file",
		GTK_WINDOW(window), GTK_FILE_CHOOSER_ACTION_SAVE, "Save", "Cancel");
	gtk_file_chooser_set_current_name(GTK_FILE_CHOOSER(chooser), "flatpak-authorized.txt");
	response = gtk_native_dialog_run(GTK_NATIVE_DIALOG(chooser));
	if (response != GTK_RESPONSE_ACCEPT) {
		g_printerr("File selection was cancelled\n");
		g_object_unref(chooser);
		return 4;
	}
	filename = gtk_file_chooser_get_filename(GTK_FILE_CHOOSER(chooser));
	if (!filename || !g_file_set_contents(filename, "flatpak-portal-grant-passed\n", -1, &error)) {
		g_printerr("Authorized write failed: %s\n", error ? error->message : "no path");
		g_clear_error(&error);
		g_free(filename);
		g_object_unref(chooser);
		return 5;
	}
	if (g_file_test(argv[1], G_FILE_TEST_EXISTS)) {
		g_printerr("File selection exposed an unrelated host file\n");
		g_free(filename);
		g_object_unref(chooser);
		return 6;
	}
	g_print("AUTHORIZED_PATH=%s\nUNAUTHORIZED_FILE_HIDDEN=true\n", filename);
	g_free(filename);
	g_object_unref(chooser);
	return 0;
}
