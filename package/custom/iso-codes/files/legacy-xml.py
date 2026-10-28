#!/usr/bin/env python3
"""Generate the legacy ISO XML tables still consumed by gnome-desktop."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

source, destination = map(Path, sys.argv[1:])
destination.mkdir(parents=True, exist_ok=True)
tables = [
    ('639-2', '639', {'alpha_2': 'iso_639_1_code', 'alpha_3': 'iso_639_2T_code',
                     'bibliographic': 'iso_639_2B_code'}),
    ('639-3', '639_3', {'alpha_3': 'id', 'alpha_2': 'part1_code'}),
    ('3166-1', '3166', {'alpha_2': 'alpha_2_code', 'alpha_3': 'alpha_3_code',
                      'numeric': 'numeric_code'}),
]
for namespace, legacy, keys in tables:
    rows = json.loads((source / f'iso_{namespace}.json').read_text())[namespace]
    root = ET.Element(f'iso_{legacy}_entries')
    for row in rows:
        attributes = {keys[key]: value for key, value in row.items() if key in keys}
        attributes.update({key: row[key] for key in ('name', 'common_name', 'official_name') if key in row})
        if namespace == '639-2':
            attributes.setdefault('iso_639_2B_code', row['alpha_3'])
        ET.SubElement(root, f'iso_{legacy}_entry', attributes)
    ET.ElementTree(root).write(destination / f'iso_{legacy}.xml',
                               encoding='utf-8', xml_declaration=True)
