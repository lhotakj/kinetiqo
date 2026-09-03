#!/usr/bin/env python3
import re
from pathlib import Path
repo = Path(r'H:/WORKING/kinetiqo')
root = repo
matches = set()
for p in root.rglob('*.html'):
    text = p.read_text(encoding='utf-8', errors='ignore')
    for m in re.findall(r"vendor/[\w\-\./]+", text):
        matches.add(m)
for p in root.rglob('*.py'):
    text = p.read_text(encoding='utf-8', errors='ignore')
    for m in re.findall(r"vendor/[\w\-\./]+", text):
        matches.add(m)

missing = []
present = []
for m in sorted(matches):
    # map to static path
    path = repo / 'src' / 'kinetiqo' / 'web' / 'static' / m
    if path.exists():
        present.append(str(m))
    else:
        missing.append(str(m))

print('Present vendor assets:')
for p in present:
    print('  ', p)
print('\nMissing vendor assets:')
for p in missing:
    print('  ', p)

# exit code non-zero if missing
if missing:
    raise SystemExit(2)
else:
    print('\nAll vendor references resolved locally.')
