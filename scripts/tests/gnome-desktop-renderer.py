#!/usr/bin/env python3
"""Report the real Wayland EGL/GLES renderer as the ordinary desktop user."""
import ctypes as C
import json
import os

assert os.getuid() >= 1000, 'Run as the desktop user'
wayland = C.CDLL('libwayland-client.so.0')
egl = C.CDLL('libEGL.so.1')
gles = C.CDLL('libGLESv2.so.2')
wayland.wl_display_connect.argtypes = [C.c_char_p]
wayland.wl_display_connect.restype = C.c_void_p
wayland.wl_display_disconnect.argtypes = [C.c_void_p]
egl.eglGetPlatformDisplay.argtypes = [C.c_uint, C.c_void_p, C.c_void_p]
egl.eglGetPlatformDisplay.restype = C.c_void_p
egl.eglInitialize.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int)]
egl.eglBindAPI.argtypes = [C.c_uint]
egl.eglChooseConfig.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_void_p),
                              C.c_int, C.POINTER(C.c_int)]
egl.eglCreateContext.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.POINTER(C.c_int)]
egl.eglCreateContext.restype = C.c_void_p
egl.eglMakeCurrent.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]
egl.eglDestroyContext.argtypes = [C.c_void_p, C.c_void_p]
egl.eglTerminate.argtypes = [C.c_void_p]
gles.glGetString.argtypes = [C.c_uint]
gles.glGetString.restype = C.c_char_p
connection = wayland.wl_display_connect(None)
assert connection, 'Cannot connect to the active Wayland session'
display = context = None
try:
    display = egl.eglGetPlatformDisplay(0x31D8, connection, None)  # WAYLAND_KHR
    major, minor = C.c_int(), C.c_int()
    assert display and egl.eglInitialize(display, C.byref(major), C.byref(minor))
    assert egl.eglBindAPI(0x30A0)  # OPENGL_ES_API
    attributes = (C.c_int * 5)(0x3033, 4, 0x3040, 4, 0x3038)  # window, ES2
    config, count = C.c_void_p(), C.c_int()
    assert egl.eglChooseConfig(display, attributes, C.byref(config), 1, C.byref(count))
    assert count.value > 0
    context_attributes = (C.c_int * 3)(0x3098, 2, 0x3038)
    context = egl.eglCreateContext(display, config, None, context_attributes)
    assert context and egl.eglMakeCurrent(display, None, None, context)
    result = {'uid': os.getuid(), 'egl_version': f'{major.value}.{minor.value}'}
    for name, value in [('vendor', 0x1F00), ('renderer', 0x1F01), ('version', 0x1F02)]:
        result[name] = gles.glGetString(value).decode()
    print(json.dumps(result, indent=2))
finally:
    if display:
        egl.eglMakeCurrent(display, None, None, None)
        if context:
            egl.eglDestroyContext(display, context)
        egl.eglTerminate(display)
    wayland.wl_display_disconnect(connection)
