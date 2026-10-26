/* Isolated desktop IME acceptance fixture; no production session access. */
#include <gtk/gtk.h>
#include <stdio.h>
static void changed(GtkEditable *entry, gpointer data) {
	FILE *f = fopen("/mnt/entry.txt", "w");
	fprintf(stderr,"changed=[%s]\n",gtk_entry_get_text(GTK_ENTRY(entry)));
	if (f) { fputs(gtk_entry_get_text(GTK_ENTRY(entry)), f); fclose(f); }
}
int main(int argc, char **argv) {
	gtk_init(&argc, &argv);
	GtkWidget *win=gtk_window_new(GTK_WINDOW_TOPLEVEL), *entry=gtk_entry_new();
	gtk_window_set_title(GTK_WINDOW(win), "Pinyin acceptance");
	gtk_window_set_default_size(GTK_WINDOW(win), 800, 600);
	gtk_window_set_decorated(GTK_WINDOW(win), FALSE);
	gtk_window_fullscreen(GTK_WINDOW(win));
	GtkWidget *box=gtk_box_new(GTK_ORIENTATION_VERTICAL,0);
	gtk_widget_set_margin_top(entry,120);
	gtk_widget_set_margin_start(entry,40);
	gtk_widget_set_margin_end(entry,40);
	gtk_box_pack_start(GTK_BOX(box),entry,FALSE,FALSE,0);
	gtk_container_add(GTK_CONTAINER(win),box);
	g_signal_connect(entry,"changed",G_CALLBACK(changed),NULL);
	g_signal_connect(win,"destroy",G_CALLBACK(gtk_main_quit),NULL);
	gtk_widget_show_all(win); gtk_widget_grab_focus(entry); gtk_main(); return 0;
}
