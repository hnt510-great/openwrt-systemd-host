// SPDX-License-Identifier: MIT
/* Run on the firmware/guest render node; no display server is required. */
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <fcntl.h>
#include <gbm.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static GLuint shader(GLenum type, const char *source)
{
	GLuint id = glCreateShader(type);
	GLint ok;

	glShaderSource(id, 1, &source, NULL);

	glCompileShader(id);
	glGetShaderiv(id, GL_COMPILE_STATUS, &ok);
	if (!ok) {
		char error[1024];

		glGetShaderInfoLog(id, sizeof(error), NULL, error);

		fprintf(stderr, "Shader compile failed: %s\n", error);
		return 0;
	}
	return id;
}

int main(int argc, char **argv)
{
	const char *node = argc > 1 ? argv[1] : "/dev/dri/renderD128";
	int fd = open(node, O_RDWR | O_CLOEXEC);

	if (fd < 0) {

		perror(node);
		return 1;
	}
	struct gbm_device *gbm = gbm_create_device(fd);

	if (!gbm) {

		fprintf(stderr, "GBM initialization failed\n");
		return 2;
	}
	PFNEGLGETPLATFORMDISPLAYEXTPROC getdisplay =
	    (PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");
	if (!getdisplay)
		return 3;
	EGLDisplay display = getdisplay(EGL_PLATFORM_GBM_KHR, gbm, NULL);
	EGLint major, minor, count;

	if (!eglInitialize(display, &major, &minor)) {

		fprintf(stderr, "EGL initialize failed: 0x%x\n", eglGetError());
		return 4;
	}
	const EGLint configattrs[] = {EGL_RENDERABLE_TYPE,
				      EGL_OPENGL_ES2_BIT,
				      EGL_RED_SIZE,
				      8,
				      EGL_GREEN_SIZE,
				      8,
				      EGL_BLUE_SIZE,
				      8,
				      EGL_NONE};
	EGLConfig config;

	if (!eglChooseConfig(display, configattrs, &config, 1, &count) || count < 1)

		return 5;
	if (!eglBindAPI(EGL_OPENGL_ES_API))
		return 6;
	const EGLint ctxattrs[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
	EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, ctxattrs);

	if (context == EGL_NO_CONTEXT ||

	    !eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, context)) {
		fprintf(stderr, "EGL context failed: 0x%x\n", eglGetError());
		return 7;
	}
	const char *renderer = (const char *)glGetString(GL_RENDERER);

	printf("EGL_VERSION=%d.%d\nGL_VENDOR=%s\nGL_RENDERER=%s\nGL_VERSION=%s\n", major, minor,

	       glGetString(GL_VENDOR), renderer, glGetString(GL_VERSION));
	if (!renderer)
		return 8;
	if (argc > 2 && strcmp(argv[2], "--require-accelerated") == 0 &&
	    (strstr(renderer, "softpipe") || strstr(renderer, "llvmpipe") ||
	     strstr(renderer, "Software"))) {
		fprintf(stderr, "Software rendering does not meet acceleration acceptance\n");
		return 9;
	}
	GLuint vs =
	    shader(GL_VERTEX_SHADER, "attribute vec2 p; void main(){gl_Position=vec4(p,0.0,1.0);}");
	GLuint fs = shader(GL_FRAGMENT_SHADER,
			   "precision mediump float; void "
			   "main(){gl_FragColor=vec4(17.0/255.0,204.0/255.0,51.0/255.0,1.0);}");
	if (!vs || !fs)
		return 10;
	GLuint program = glCreateProgram();

	glAttachShader(program, vs);

	glAttachShader(program, fs);
	glBindAttribLocation(program, 0, "p");
	glLinkProgram(program);
	GLint linked;

	glGetProgramiv(program, GL_LINK_STATUS, &linked);

	if (!linked)
		return 11;
	GLuint texture, fbo;

	glGenTextures(1, &texture);

	glBindTexture(GL_TEXTURE_2D, texture);
	glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 64, 64, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
	glGenFramebuffers(1, &fbo);
	glBindFramebuffer(GL_FRAMEBUFFER, fbo);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0);
	if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
		return 12;
	const GLfloat vertices[] = {-1, -1, 3, -1, -1, 3};
	glViewport(0, 0, 64, 64);
	glUseProgram(program);
	glEnableVertexAttribArray(0);
	glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, vertices);
	glDrawArrays(GL_TRIANGLES, 0, 3);
	unsigned char pixel[4] = {0};

	glReadPixels(32, 32, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, pixel);

	printf("SHADER_PIXEL=%u,%u,%u,%u\n", pixel[0], pixel[1], pixel[2], pixel[3]);
	if (glGetError() != GL_NO_ERROR || pixel[0] != 17 || pixel[1] != 204 || pixel[2] != 51 ||
	    pixel[3] != 255)
		return 13;
	glDeleteFramebuffers(1, &fbo);
	glDeleteTextures(1, &texture);
	glDeleteProgram(program);
	glDeleteShader(vs);
	glDeleteShader(fs);
	eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
	eglDestroyContext(display, context);
	eglTerminate(display);
	gbm_device_destroy(gbm);
	close(fd);
	puts("EGL_SHADER_RENDER_PASSED");
	return 0;
}
