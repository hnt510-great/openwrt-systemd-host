#!/usr/bin/env python3
"""Compile the patched GRD playback policy and exercise latency/ACK regressions.

The C functions come from the release archive with the package patches applied.
Only the clock, mutexes and pending-frame queue are replaced by test fixtures.
This checks the drop policy, not RDP transport, threading or audible playback.
GRD_AUDIO_PATCH can override patch 005 to demonstrate the original regression.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef int gboolean;
#define TRUE 1
#define FALSE 0
#define G_USEC_PER_SEC 1000000
#define CHANNEL_RC_OK 0
#define MAX(a,b) ((a) > (b) ? (a) : (b))
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#define MAX_RENDER_LATENCY_MS 300
#define BASELINE_BUCKET_US (5 * G_USEC_PER_SEC)
#define MAX_UNACKED_BLOCK_AGE_US (2 * G_USEC_PER_SEC)
/* Superset keeps the old ACK policy executable for the regression control. */
typedef struct {
  uint16_t render_latency_ms;
  int64_t render_latency_set_us, sent_us;
  gboolean acknowledged;
} BlockInfo;
typedef struct {
  gboolean valid;
  int64_t bucket_start_us;
  uint32_t current_min_ms, previous_min_ms;
} DelayBaseline;
typedef struct { unsigned frames, drops; } Queue;
typedef struct {
  BlockInfo block_infos[256];
  DelayBaseline render_latency_baseline, ack_delay_baseline;
  int block_mutex;
  Queue *pending_frames;
} GrdRdpDvcAudioPlayback;
typedef struct { GrdRdpDvcAudioPlayback *data; } RdpsndServerContext;
static int64_t now;
#define g_get_monotonic_time() now
#define g_mutex_lock(mutex) ((void)(mutex))
#define g_mutex_unlock(mutex) ((void)(mutex))
#define g_debug(...) ((void)0)
#define g_queue_clear_full(queue, destroy) \
  do { (queue)->frames = 0; ++(queue)->drops; } while (0)
'''

PROGRAM = r'''
int main(int argc, char **argv) {
  assert(argc == 2);
  const char *test = argv[1];
  Queue queue = {0};
  GrdRdpDvcAudioPlayback playback = {.pending_frames = &queue};
  RdpsndServerContext context = {.data = &playback};
  reset_block_infos(&playback);
  for (unsigned i = 0; i < 256; ++i)
    playback.block_infos[i].acknowledged = TRUE;

  if (!strcmp(test, "no-confirmations")) {
    for (unsigned ms = 0; ms < 15000; ms += 10) {
      now = (int64_t)ms * 1000;
      queue.frames = 1;
      maybe_drop_pending_frames(&playback);
      assert(queue.frames == 1);
    }
  } else if (!strcmp(test, "missing-ack") || !strcmp(test, "delayed-ack")) {
    delay_baseline_add_sample(&playback.ack_delay_baseline, 1, 0);
    rdpsnd_confirm_block(&context, 1, 520);
    playback.block_infos[0].acknowledged = FALSE;
    playback.block_infos[0].sent_us = 0;
    for (unsigned ms = 10; ms < 15000; ms += 10) {
      now = (int64_t)ms * 1000;
      if (!strcmp(test, "delayed-ack") && ms == 700)
        rdpsnd_confirm_block(&context, 0, 520);
      /* Later blocks play and confirm normally; block zero must not mute them. */
      rdpsnd_confirm_block(&context, 1 + (ms / 10) % 255, 520);
      queue.frames = 1;
      maybe_drop_pending_frames(&playback);
      assert(queue.frames == 1);
    }
  } else if (!strcmp(test, "congestion") || !strcmp(test, "device-switch")) {
    for (unsigned ms = 0; ms < 15000; ms += 10) {
      now = (int64_t)ms * 1000;
      unsigned latency = ms < 1000 ? 520 :
                         !strcmp(test, "congestion") ? 520 + (ms - 1000) / 2 : 1000;
      rdpsnd_confirm_block(&context, (ms / 10) % 256, latency);
      queue.frames = 1;
      maybe_drop_pending_frames(&playback);
      if (ms == 3000) assert(queue.drops > 0);
      /* A permanent new device delay must be accepted after baseline expiry. */
      if (ms >= 12000 && !strcmp(test, "device-switch")) assert(queue.frames == 1);
    }
  } else if (!strcmp(test, "stream-reset")) {
    rdpsnd_confirm_block(&context, 0, 10);
    reset_block_infos(&playback);
    now = 20000;
    rdpsnd_confirm_block(&context, 0, 1500);
    queue.frames = 1;
    maybe_drop_pending_frames(&playback);
    assert(queue.frames == 1);
  } else if (!strcmp(test, "idle-resume")) {
    rdpsnd_confirm_block(&context, 0, 10);
    now = 20000000;
    rdpsnd_confirm_block(&context, 0, 1500);
    queue.frames = 1;
    maybe_drop_pending_frames(&playback);
    assert(queue.frames == 1);
  } else {
    unsigned base = !strcmp(test, "low-latency") ? 20 :
                    !strcmp(test, "very-slow-device") ? 3000 : 520;
    for (unsigned ms = 0; ms < 30000; ms += 10) {
      now = (int64_t)ms * 1000;
      unsigned jitter = !strcmp(test, "jitter") ? (ms / 10) % 40 : 0;
      rdpsnd_confirm_block(&context, (ms / 10) % 256, base + jitter);
      queue.frames = 1;
      maybe_drop_pending_frames(&playback);
      assert(queue.frames == 1);
    }
  }
  printf("%s: passed (%u drops)\n", test, queue.drops);
  return 0;
}
'''


def function(source, name):
    match = re.search(r'static (?:void|gboolean|uint32_t)\n' + name + r'\s*\(', source)
    if match is None:
        return ''
    end = source.index('\n}\n', match.start()) + 3
    return source[match.start():end]


class AudioLatencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archive = ROOT / 'dl/gnome-remote-desktop-51.0.tar.xz'
        if not archive.exists():
            raise unittest.SkipTest('download gnome-remote-desktop first')
        cls.temporary = tempfile.TemporaryDirectory(prefix='grd-audio-latency-')
        cls.addClassCleanup(cls.temporary.cleanup)
        work = Path(cls.temporary.name)
        subprocess.run(['tar', '-xf', str(archive), '-C', str(work)], check=True)
        tree = work / 'gnome-remote-desktop-51.0'
        for patch in sorted((ROOT / 'package/custom/gnome-remote-desktop/patches').glob('*.patch')):
            if patch.name.startswith('005-') and os.environ.get('GRD_AUDIO_PATCH'):
                patch = Path(os.environ['GRD_AUDIO_PATCH']).resolve()
            subprocess.run(['patch', '-p1', '--fuzz=0', '-i', str(patch)],
                           cwd=tree, check=True, capture_output=True)
        source = (tree / 'src/grd-rdp-dvc-audio-playback.c').read_text()
        names = ['delay_baseline_add_sample', 'delay_baseline_get', 'reset_block_infos',
                 'rdpsnd_confirm_block', 'get_current_render_latency',
                 'get_oldest_unacknowledged_block_age', 'get_queueing_delay',
                 'maybe_drop_pending_frames']
        code = PREFIX + '\n'.join(function(source, name) for name in names) + PROGRAM
        program = work / 'policy.c'
        program.write_text(code)
        cls.binary = work / 'policy'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
                        str(program), '-o', str(cls.binary)], check=True)

    def test_playback_policy(self):
        cases = ['constant-520ms', 'low-latency', 'very-slow-device', 'jitter',
                 'missing-ack', 'delayed-ack', 'no-confirmations', 'congestion',
                 'device-switch', 'stream-reset', 'idle-resume']
        for case in cases:
            with self.subTest(case=case):
                subprocess.run([str(self.binary), case], check=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
