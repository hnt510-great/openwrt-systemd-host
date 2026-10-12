// Software rendering and decoding are the default for the lightweight desktop.
// Keep the browser's content, GPU and media process sandbox settings unchanged.
pref("gfx.webrender.software", true);
pref("media.hardware-video-decoding.enabled", false);
