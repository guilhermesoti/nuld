#pragma once
// UI language indices: 0 Spanish, 1 English, 2 Brazilian Portuguese (default).
extern int lang_en; // historical name; shared with indexed label tables
#define LANG_PT_BR 2
#define L(es, en, pt) (lang_en == LANG_PT_BR ? (pt) : lang_en == 1 ? (en) : (es))

#include <strings.h>
static inline int ui_language(const char *value)
{
    if (!strcasecmp(value, "en")) return 1;
    if (!strcasecmp(value, "es")) return 0;
    return LANG_PT_BR; // pt, pt-BR, pt_BR and unknown values use the fork default
}
