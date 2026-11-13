#!/usr/bin/env python3
"""Check the UI translations' printf arguments and host language selection."""
import json, re, subprocess, tempfile
from pathlib import Path
root = Path(__file__).resolve().parent.parent
string = r'"(?:[^"\\]|\\.)*"'
arg = rf'(?:{string}\s*)+'
pattern = re.compile(rf'\bL\(\s*({arg}),\s*({arg}),\s*({arg})\)')
fmt = re.compile(r'%(?:[-+ #0]*\d*(?:\.\d+)?[hlz]*[diuoxXfFeEgGcsp]|%)')
count = 0
for file in ('launcher.c', 'sources.c'):
    src = (root / file).read_text()
    matches = list(pattern.finditer(src))
    assert len(matches) == len(re.findall(r'\bL\(', src)), f'{file}: missing translation'
    for m in matches:
        parts = [''.join(json.loads(x) for x in re.findall(string, a)) for a in m.groups()]
        assert parts[2], f'{file}: empty pt-BR text'
        assert fmt.findall(parts[1]) == fmt.findall(parts[2]), parts
    count += len(matches)
with tempfile.TemporaryDirectory() as folder:
    src = Path(folder) / 'lang_test.c'
    src.write_text('''#include <assert.h>
#include <string.h>
#include "lang.h"
int lang_en = LANG_PT_BR;
int main(void) {
 assert(ui_language("pt-BR") == 2 && ui_language("pt") == 2 && ui_language("pt_BR") == 2);
 assert(ui_language("en") == 1 && ui_language("es") == 0 && ui_language("unknown") == 2);
 for (lang_en = 0; lang_en < 3; lang_en++)
   assert(!strcmp(L("es", "en", "pt"), lang_en == 0 ? "es" : lang_en == 1 ? "en" : "pt"));
 return 0;
}
''')
    subprocess.run(['cc', '-std=c99', '-Wall', '-Werror', '-I', str(root), str(src), '-o', str(Path(folder) / 'lang_test')], check=True)
    subprocess.run([str(Path(folder) / 'lang_test')], check=True)
print(f'pt-BR: {count} translated calls, printf arguments and language selection OK')
