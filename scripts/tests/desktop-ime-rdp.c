/* Isolated RDP input fixture; uses only the test namespace and test account. */
#include <freerdp/freerdp.h>
#include <freerdp/gdi/gdi.h>
#include <freerdp/input.h>
#include <freerdp/client.h>
#include <freerdp/client/channels.h>
#include <freerdp/client/cmdline.h>
#include <freerdp/settings.h>
#include <winpr/synch.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
static BOOL begin(rdpContext *c) {c->gdi->primary->hdc->hwnd->invalid->null=TRUE;return TRUE;}
static BOOL end(rdpContext *c) {return TRUE;}
static BOOL post(freerdp *f) {if(!gdi_init(f,PIXEL_FORMAT_XRGB32))return FALSE;f->context->update->BeginPaint=begin;f->context->update->EndPaint=end;return TRUE;}
static void pump(freerdp *f, int ms) {
	for (int i=0;i<ms/10;i++) {
		HANDLE h[64]; DWORD n=freerdp_get_event_handles(f->context,h,64);
		if(n) WaitForMultipleObjects(n,h,FALSE,10);
		usleep(10000);
		if(!freerdp_check_event_handles(f->context)) {fprintf(stderr,"pump failed\n");return;}
	}
}
static void key(freerdp *f, int code, BOOL down) {
	if (!freerdp_input_send_keyboard_event(f->context->input, down ? 0 : KBD_FLAGS_RELEASE, code)) {
		fprintf(stderr, "RDP key send failed\n");
		exit(4);
	}
	pump(f,40);
}
static void tap(freerdp *f, int code) { key(f,code,TRUE);key(f,code,FALSE); }
static void toggle(freerdp *f) {
	key(f,0x1d,TRUE);key(f,0x2a,TRUE);tap(f,0x39);key(f,0x2a,FALSE);key(f,0x1d,FALSE);pump(f,500);
}
static BOOL pre(freerdp *f) {
	return freerdp_client_load_addins(f->context->channels, f->context->settings);
}
static BOOL client_new(freerdp *f, rdpContext *c) { f->PreConnect=pre; f->PostConnect=post;return TRUE; }
int main(void) {
	freerdp_register_addin_provider(freerdp_channels_load_static_addin_entry,0);
	RDP_CLIENT_ENTRY_POINTS e={0};e.Size=sizeof(e);e.Version=RDP_CLIENT_INTERFACE_VERSION;
	e.ContextSize=sizeof(rdpClientContext);e.ClientNew=client_new;
	rdpContext *ctx=freerdp_client_context_new(&e);if(!ctx)return 2;
	freerdp *f=ctx->instance;
	rdpSettings *s=f->context->settings;
	freerdp_settings_set_string(s,FreeRDP_ServerHostname,"127.0.0.1");
	freerdp_settings_set_uint32(s,FreeRDP_ServerPort,33991);
	freerdp_settings_set_string(s,FreeRDP_Username,"ime");
	freerdp_settings_set_string(s,FreeRDP_Password,"ime-test-only");
	freerdp_settings_set_uint32(s,FreeRDP_DesktopWidth,800);
	freerdp_settings_set_uint32(s,FreeRDP_DesktopHeight,600);
	freerdp_settings_set_uint32(s,FreeRDP_ColorDepth,32);
	freerdp_settings_set_bool(s,FreeRDP_IgnoreCertificate,TRUE);
	freerdp_settings_set_bool(s,FreeRDP_NlaSecurity,TRUE);
	freerdp_settings_set_bool(s,FreeRDP_TlsSecurity,TRUE);
	freerdp_settings_set_bool(s,FreeRDP_RdpSecurity,FALSE);
	freerdp_settings_set_bool(s,FreeRDP_Authentication,TRUE);
	if(!freerdp_connect(f)){fprintf(stderr,"connect failed: %x\n",freerdp_get_last_error(f->context));return 3;}
	pump(f,2000);
	freerdp_input_send_mouse_event(f->context->input,PTR_FLAGS_MOVE,200,135);
	freerdp_input_send_mouse_event(f->context->input,PTR_FLAGS_BUTTON1|PTR_FLAGS_DOWN,200,135);
	freerdp_input_send_mouse_event(f->context->input,PTR_FLAGS_BUTTON1,200,135);
	pump(f,700);toggle(f);system("fcitx5-remote > /mnt/state1");
	int codes[]={0x31,0x17,0x23,0x1e,0x18};for(int i=0;i<5;i++)tap(f,codes[i]);
	pump(f,1500);
	system("XDG_PICTURES_DIR=/mnt weston-screenshooter");
	tap(f,0x39);pump(f,1500);system("cat /mnt/entry.txt > /mnt/after-commit");toggle(f);system("fcitx5-remote > /mnt/state2");
	int en[]={0x1e,0x30,0x2e};for(int i=0;i<3;i++)tap(f,en[i]);pump(f,1500);
	freerdp_disconnect(f);gdi_free(f);freerdp_client_context_free(ctx);return 0;
}
