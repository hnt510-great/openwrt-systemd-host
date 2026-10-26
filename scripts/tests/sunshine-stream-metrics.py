#!/usr/bin/env python3
"""Decode a synthetic capture probe and measure received frames and input changes.

The fixture must have a black/white input indicator in the left half. Latency
ends when the encoded frame reaches the receiver; offline decoding associates
that frame with its pixels. Client display/decoder latency is not included.
"""
import argparse
import csv
import json
from pathlib import Path
import statistics
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prefix', type=Path)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--height', type=int, default=1080)
    args = parser.parse_args()
    prefix = str(args.prefix)
    rows = list(csv.reader(Path(prefix + '.csv').open()))
    frames = [row for row in rows if row[0] == 'frame']
    inputs = [float(row[1]) for row in rows if row[0] == 'input']
    if len(frames) < 2:
        raise SystemExit('Not enough received frames')
    pixels = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', prefix + '.h264',
                                      '-vf', f'crop=16:16:{args.width // 4}:{args.height // 2},scale=1:1',
                                      '-pix_fmt', 'gray', '-f', 'rawvideo', '-'])
    hashes = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', prefix + '.h264',
                                      '-vf', 'scale=32:18', '-pix_fmt', 'gray', '-f', 'framemd5', '-'], text=True)
    hashes = [line.rsplit(',', 1)[1].strip() for line in hashes.splitlines() if line and not line.startswith('#')]
    if len(pixels) != len(frames) or len(hashes) != len(frames):
        raise SystemExit(f'Decode mismatch: {len(frames)} received, {len(pixels)} pixel samples, {len(hashes)} hashes')
    changes = [i for i in range(1, len(pixels)) if (pixels[i] > 128) != (pixels[i - 1] > 128)]
    latency = []
    for sent in inputs:
        candidates = [float(frames[i][3]) - sent for i in changes if 0 < float(frames[i][3]) - sent < .5]
        if candidates:
            latency.append(min(candidates) * 1000)
    gaps = [(float(b[3]) - float(a[3])) * 1000 for a, b in zip(frames, frames[1:])]
    duration = float(frames[-1][3]) - float(frames[0][3])
    percentile = lambda values: sorted(values)[int((len(values) - 1) * .95)] if values else None
    distinct = 1 + sum(a != b for a, b in zip(hashes, hashes[1:]))
    result = {'received_frames': len(frames), 'decoded_frames': len(pixels),
              'received_fps': (len(frames) - 1) / duration,
              'distinct_frame_fps': (distinct - 1) / duration,
              'frame_gap_p95_ms': percentile(gaps), 'input_events': len(inputs),
              'detected_input_changes': len(latency),
              'input_to_received_frame_median_ms': statistics.median(latency) if latency else None,
              'input_to_received_frame_p95_ms': percentile(latency),
              'host_processing_p95_ms': percentile([int(row[5]) / 10 for row in frames]),
              'encoded_mbit_per_second': Path(prefix + '.h264').stat().st_size * 8 / duration / 1e6,
              'audio_summary': next((row[1:] for row in reversed(rows) if row[0] == 'summary'), None)}
    before, after = Path(prefix + '-before.json'), Path(prefix + '-after.json')
    if before.exists() and after.exists():
        before, after = json.loads(before.read_text()), json.loads(after.read_text())
        elapsed = after['time'] - before['time']
        result['cpu_percent_one_core'] = {
            role: (value['ticks'] - before['processes'][role]['ticks']) / after['hz'] / elapsed * 100
            for role, value in after['processes'].items()
            if role in before['processes'] and value['pid'] == before['processes'][role]['pid']}
    Path(prefix + '-results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
