#!/bin/zsh
# Validate every archify source under visual/sources.
SKILL=/Users/vijeshshetty/.config/opencode/skills/archify
ROOT=/Users/vijeshshetty/Documents/projects/catalyst
SRC=$ROOT/visual/sources
types=(sequence sequence workflow lifecycle dataflow workflow)
names=(serve-path toggle-propagation provisioning sdk-client-lifecycle evaluation-dataflow release-pipeline)
for i in {1..6}; do
  t=$types[$i]; n=$names[$i]
  echo "════ $t / $n"
  (cd $SKILL && node bin/archify.mjs validate $t "$SRC/$n.json" --quality showcase --json 2>&1) | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('  ok:',d.get('ok'),' checks:',len(d.get('checks',[])),' diags:',len(d.get('diagnostics',[])))
for x in d.get('diagnostics',[])[:7]:
    print('  -',x['code'],'::',x['message'][:200].replace(chr(10),' '))
"
done
