"""Check active manuscript assets, citation keys, labels, and environments."""
from pathlib import Path
import re
import json

root = Path(__file__).resolve().parents[1]
files = [root / 'main.tex'] + sorted((root / 'contents').glob('*.tex'))
texts = {p: re.sub(r'(?<!\\)%[^\n]*', '', p.read_text(encoding='utf-8'))
         for p in files}
bib = (root / 'myrefs.bib').read_text(encoding='utf-8')
keys = set(re.findall(r'@\w+\s*\{\s*([^,\s]+)', bib))
labels = []
errors = []
for path, text in texts.items():
    labels += re.findall(r'\\label\{([^}]+)\}', text)
    stack = []
    for match in re.finditer(r'\\(begin|end)\{([^}]+)\}', text):
        kind, name = match.groups()
        if kind == 'begin':
            stack.append(name)
        elif not stack or stack.pop() != name:
            errors.append(f'{path.name}: mismatched environment {name}')
    if stack:
        errors.append(f'{path.name}: unclosed environments {stack}')
    for asset in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', text):
        if not (root / asset).is_file():
            errors.append(f'{path.name}: missing image {asset}')
    for group in re.findall(r'\\(?:cite|citep|citet|autocite)(?:\[[^\]]*\])*\{([^}]+)\}', text):
        for key in group.split(','):
            if key.strip() not in keys:
                errors.append(f'{path.name}: missing citation {key.strip()}')
for path, text in texts.items():
    for name in re.findall(r'\\(?:ref|eqref|pageref)\{([^}]+)\}', text):
        if not name.startswith('#') and name not in labels:
            errors.append(f'{path.name}: missing label {name}')
errors.extend(f'duplicate label: {name}' for name in sorted(set(labels))
              if labels.count(name) > 1)
print(json.dumps({'files': len(files), 'citation_keys': len(keys),
    'labels': len(labels), 'errors': errors,
    'scope': 'Static checks only; compilation and visual QA required.'},
    ensure_ascii=False, indent=2))
raise SystemExit(bool(errors))
