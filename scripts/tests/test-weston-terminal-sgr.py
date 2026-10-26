#!/usr/bin/env python3
"""Compile and exercise the patched Weston SGR implementation itself."""
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'feeds/video/frameworks/weston/patches/010-terminal-consume-rgb-sgr-colors.patch'


def function(source, name):
    match = re.search(r'static (?:void|int)\n' + name + r'\([^;]+?\)\n\{', source)
    start = match.start()
    end = source.index('\n}', start) + 2
    return source[start:end]


class TerminalSgr(unittest.TestCase):
    def test_extended_colors_and_attributes(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / 'clients').mkdir()
            with tarfile.open(ROOT / 'dl/weston-16.0.0.tar.xz') as archive:
                source = archive.extractfile('weston-16.0.0/clients/terminal.c').read()
            (work / 'clients/terminal.c').write_bytes(source)
            subprocess.run(['patch', '-p1', '-i', str(PATCH)], cwd=work, check=True,
                           capture_output=True)
            source = (work / 'clients/terminal.c').read_text()
            harness = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define ATTRMASK_BOLD 1
#define ATTRMASK_UNDERLINE 2
#define ATTRMASK_BLINK 4
#define ATTRMASK_CONCEALED 8
#define ATTRMASK_INVERSE 16
struct terminal_color { double r, g, b, a; };
struct attr { unsigned char fg, bg; char a, s; };
struct color_scheme { struct terminal_color palette[16]; char border; struct attr default_attr; };
struct terminal { struct attr curr_attr; struct color_scheme *color_scheme;
                  struct terminal_color color_table[256]; };
'''
            for name in ['init_color_table', 'handle_sgr', 'terminal_rgb_index',
                         'terminal_handle_sgr']:
                harness += function(source, name) + '\n'
            harness += r'''
static void apply(struct terminal *t, int *args, int n) {
    int set[10] = {0};
    for (int i = 0; i < n; i++) set[i] = 1;
    terminal_handle_sgr(t, args, set, 10);
}
#define APPLY(...) do { int args[10] = {__VA_ARGS__}; \
    apply(&t, args, sizeof((int[]){__VA_ARGS__}) / sizeof(int)); } while (0)
int main(void) {
    struct color_scheme scheme = { .default_attr = {7, 0, 0, 0} };
    struct terminal t = { .color_scheme = &scheme };
    init_color_table(&t);
    /* Exact reported RGB components, and following underline. */
    APPLY(38, 2, 250, 179, 135, 4);
    assert(t.curr_attr.fg == terminal_rgb_index(&t, 250, 179, 135));
    assert(t.curr_attr.a == ATTRMASK_UNDERLINE);
    APPLY(0, 38, 5, 244, 48, 5, 148, 4);
    assert(t.curr_attr.fg == 244 && t.curr_attr.bg == 148);
    assert(t.curr_attr.a == ATTRMASK_UNDERLINE);
    /* Both RGB colors fill all ten argument slots. */
    APPLY(38, 2, 250, 179, 135, 48, 2, 244, 148, 135);
    assert(t.curr_attr.bg == terminal_rgb_index(&t, 244, 148, 135));
    APPLY(0, 38, 2, 1, 4); /* truncated: do not set bold/underline */
    assert(t.curr_attr.fg == 7 && t.curr_attr.a == 0);
    APPLY(38, 5, 256); /* must not wrap into background codes */
    assert(t.curr_attr.fg == 7 && t.curr_attr.bg == 0);
    APPLY(48, 2, 255, 256, 4);
    assert(t.curr_attr.bg == 0 && t.curr_attr.a == 0);
    APPLY(38, 3, 1, 4); /* unknown color mode */
    assert(t.curr_attr.a == 0);
    APPLY(31, 44, 4);
    assert(t.curr_attr.fg == 1 && t.curr_attr.bg == 4);
    APPLY(39, 49, 24);
    assert(t.curr_attr.fg == 7 && t.curr_attr.bg == 0 && t.curr_attr.a == 0);
    int args[10] = {0}, set[10] = {0};
    t.curr_attr.a = ATTRMASK_BOLD;
    terminal_handle_sgr(&t, args, set, 10);
    assert(t.curr_attr.a == 0);
    return 0;
}
'''
            (work / 'test.c').write_text(harness)
            subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                            str(work / 'test.c'), '-o', str(work / 'test')], check=True)
            result = subprocess.run([str(work / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
