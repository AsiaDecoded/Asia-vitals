#!/bin/sh
# Assemble index.html (the page document) from style.css, body.html and jg.js, as for dashboards/in.
cd "$(dirname "$0")"
{ printf '<style>\n'; cat style.css; printf '</style>\n\n\n\n'; cat body.html; printf '\n<script>\nconst num = (v) => (v === %s || v == null ? null : Number(v));\n' "''"; cat jg.js; printf '\n</script>\n<script src="app.js"></script>\n<script src="export.js"></script>\n'; } > index.html
