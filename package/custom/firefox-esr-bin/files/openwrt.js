// Let Firefox detect EGL/WebRender and VA-API, with software fallback.
// Keep the browser's content, GPU and media process sandbox settings unchanged.
pref("media.hardware-video-decoding.enabled", true);
