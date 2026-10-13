/* SPDX-License-Identifier: MIT */
#include <GL/gl.h>
#include <GL/glx.h>
#include <stdio.h>
#include <stdlib.h>

int main(void)
{
	int attributes[] = { GLX_RGBA, GLX_RED_SIZE, 8, GLX_GREEN_SIZE, 8,
		GLX_BLUE_SIZE, 8, None };
	Display *display = XOpenDisplay(NULL);
	XVisualInfo *visual;
	XSetWindowAttributes window_attributes;
	GLXContext context;
	Window window;
	unsigned char pixel[4];
	int major, minor, failed;

	if (!display || !glXQueryVersion(display, &major, &minor)) {
		fputs("GLX display unavailable\n", stderr);
		return 1;
	}
	visual = glXChooseVisual(display, DefaultScreen(display), attributes);
	if (!visual) {
		fputs("GLX visual unavailable\n", stderr);
		XCloseDisplay(display);
		return 1;
	}
	window_attributes.colormap = XCreateColormap(display,
		RootWindow(display, visual->screen), visual->visual, AllocNone);
	window_attributes.event_mask = StructureNotifyMask;
	window = XCreateWindow(display, RootWindow(display, visual->screen),
		0, 0, 64, 64, 0, visual->depth, InputOutput, visual->visual,
		CWColormap | CWEventMask, &window_attributes);
	XMapWindow(display, window);
	XSync(display, False);
	context = glXCreateContext(display, visual, NULL, True);
	if (!context || !glXMakeCurrent(display, window, context)) {
		fputs("GLX context unavailable\n", stderr);
		return 1;
	}
	glViewport(0, 0, 64, 64);
	glClearColor(17.0f / 255, 204.0f / 255, 51.0f / 255, 1);
	glClear(GL_COLOR_BUFFER_BIT);
	glFinish();
	glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, pixel);
	printf("GLX_VERSION=%d.%d\nGL_RENDERER=%s\nGL_VERSION=%s\n",
		major, minor, glGetString(GL_RENDERER), glGetString(GL_VERSION));
	printf("GLX_PIXEL=%u,%u,%u,%u\n", pixel[0], pixel[1], pixel[2], pixel[3]);
	failed = abs((int)pixel[0] - 17) > 1 || abs((int)pixel[1] - 204) > 1 ||
		abs((int)pixel[2] - 51) > 1 || glGetError() != GL_NO_ERROR;
	glXMakeCurrent(display, None, NULL);
	glXDestroyContext(display, context);
	XDestroyWindow(display, window);
	XFreeColormap(display, window_attributes.colormap);
	XFree(visual);
	XCloseDisplay(display);
	return failed;
}
