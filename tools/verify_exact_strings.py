from pathlib import Path

files = [
    'DOCS/QUANTVIEW_MASTER_SPEC.md',
    'DOCS/QUANTVIEW_DATA_SPEC.md',
    'DOCS/QUANTVIEW_ENGINE_UI_RESEARCH_SPEC.md',
    'DOCS/AGENTS.md'
]

targets = [
    'single-use per strategy version',
    'single-use per version',
    'per strategy version',
    'UNIQUE(strategy_id, strategy_version)',
    'final_eval=true',
    'MASTER §5 owner decisions'
]

all_clean = True
for target in targets:
    found = []
    for f in files:
        text = Path(f).read_text(encoding='utf-8')
        count = text.count(target)
        if count > 0:
            found.append(f'{f} ({count} occurrences)')
    if found:
        print(f'FAIL: "{target}" found in: {", ".join(found)}')
        all_clean = False
    else:
        print(f'PASS: "{target}" -> 0 occurrences across all 4 files')

if not all_clean:
    raise SystemExit(1)
print('\nALL EXACT-STRING LITERAL CHECKS PASSED: ZERO OCCURRENCES!')
