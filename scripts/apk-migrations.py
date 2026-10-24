#!/usr/bin/env python3
"""Validate explicit empty-package migrations and emit normal kernel recipes."""
import argparse
import json
from pathlib import Path
import re


def rules(path):
    data = json.loads(Path(path).read_text())
    if data.get('schema') != 1 or not isinstance(data.get('rules'), list):
        raise ValueError('Unsupported APK migration schema')
    result = {}
    for rule in data['rules']:
        old, targets = rule.get('from'), rule.get('to')
        names = [old, *(targets if isinstance(targets, list) else [])]
        if (not isinstance(targets, list) or not targets or
                any(not isinstance(n, str) or not re.fullmatch(r'[a-z0-9][a-z0-9+_.-]*', n) for n in names) or
                rule.get('type') != 'empty-compat' or not rule.get('reason') or
                old in targets or old in result or len(set(targets)) != len(targets)):
            raise ValueError('Invalid or duplicate empty-package migration: ' + str(old))
        if not old.startswith('kmod-') or any(not n.startswith('kmod-') for n in targets):
            raise ValueError('Automatic compatibility generation currently supports kernel packages only')
        result[old] = rule
    def visit(name, ancestors):
        if name in ancestors:
            raise ValueError('Cyclic APK migration: ' + name)
        for target in result.get(name, {}).get('to', []):
            visit(target, ancestors | {name})
    for name in result:
        visit(name, set())
    return result


def make_recipes(path):
    return '\n'.join('$(eval $(call KernelCompatibility,' + name[5:] + ',' +
                     ' '.join(rule['to']) + '))' for name, rule in sorted(rules(path).items()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--make', type=Path, required=True)
    args = parser.parse_args()
    print(make_recipes(args.make))
