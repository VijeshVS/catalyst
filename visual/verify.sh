#!/bin/zsh
# Bounded desktop browser evidence for every delivered artifact.
SKILL=/Users/vijeshshetty/.config/opencode/skills/archify
ROOT=/Users/vijeshshetty/Documents/projects/catalyst
OUT=$ROOT/visual/artifacts
EVID=/var/folders/59/_3gnhjdj55g314r2npjrxst80000gn/T/opencode/catalyst-visual-evidence
mkdir -p $EVID
names=(runtime-architecture serve-path toggle-propagation provisioning sdk-client-lifecycle evaluation-dataflow release-pipeline)
for n in $names; do
  printf '%-26s ' "$n"
  # visual-check writes sidecars next to the artifact; move them out of the repo
  (cd $SKILL && node bin/archify.mjs visual-check "$OUT/$n.html" --json 2>&1) | python3 -c "
import json,sys
d=json.load(sys.stdin)
c=d['containment']; r=d['readability']
bad=[v for v in c['viewports'] if v['overflowY'] or v['overflowX']]
mn=min(v['minimumProjectedNodeTextPx'] for v in c['viewports'])
print(f\"contain={c['status']:5s} readability={r['status']:5s} minText={mn:.2f}px  overflow@{[str(v['width'])+'x'+str(v['height']) for v in bad] or 'none'}\")
" || echo "  (visual-check reported a non-zero exit)"
  mv "$OUT/$n".visual-check.* "$EVID"/ 2>/dev/null
done
