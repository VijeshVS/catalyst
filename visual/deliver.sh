#!/bin/zsh
# Deliver every archify source into visual/artifacts/ and report the receipts.
SKILL=/Users/vijeshshetty/.config/opencode/skills/archify
ROOT=/Users/vijeshshetty/Documents/projects/catalyst
SRC=$ROOT/visual/sources
OUT=$ROOT/visual/artifacts
types=(architecture sequence sequence workflow lifecycle dataflow workflow)
names=(runtime-architecture serve-path toggle-propagation provisioning sdk-client-lifecycle evaluation-dataflow release-pipeline)
fail=0
for i in {1..7}; do
  t=$types[$i]; n=$names[$i]
  printf '%-26s ' "$n"
  extra=(); [[ $t == architecture ]] && extra=(--repo-root "$ROOT")
  (cd $SKILL && node bin/archify.mjs deliver $t "$SRC/$n.json" "$OUT/$n.html" --quality showcase $extra --json 2>&1) | python3 -c "
import json,sys
d=json.load(sys.stdin)
if d.get('ok'):
    v=d['validation']; s=d['specification']; a=d['artifact']
    print(f\"OK  checks {v['checksPassed']}/{v['checkCount']}  err {v['errors']}  warn {v['warnings']}  spec {s['sha256'][:12]}  html {a['bytes']:,}B\")
else:
    print('FAIL')
    for x in d.get('diagnostics',[])[:4]: print('    -',x['code'],'::',x['message'][:150].replace(chr(10),' '))
    sys.exit(1)
" || fail=1
done
exit $fail
