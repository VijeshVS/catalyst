# Catalyst Visual

Seven interactive, source-backed diagrams of how the Catalyst feature flag platform actually
runs. Each one is generated from a typed JSON source, validated against layout and composition
rules, and delivered as a single self-contained HTML file.

Everything here is produced by [Archify](https://github.com/tt-a1i/archify). Nothing is drawn
by hand, and every architectural claim carries a `file:line` citation into this repository.

## The diagrams

| # | Page | Type | What it covers |
|---|------|------|----------------|
| 01 | [Runtime Architecture](runtime-architecture.html) | Architecture | Components, external dependencies, and the four trust boundaries |
| 02 | [SDK Flag Check](serve-path.html) | Sequence | The conditional read, the 304 short-circuit, and the cold-path rebuild |
| 03 | [Toggle Propagation](toggle-propagation.html) | Sequence | A dashboard mutation reaching the next SDK read, and why it cannot be stale |
| 04 | [Tenant Onboarding](provisioning.html) | Workflow | Register → organization → project → environments → first flag |
| 05 | [SDK Client Lifecycle](sdk-client-lifecycle.html) | Lifecycle | Read-path states, the recoverable backoff window, and the one terminal failure |
| 06 | [Evaluation Data Flow](evaluation-dataflow.html) | Data Flow | Where caller attributes cross the wire and where they stop travelling |
| 07 | [Release Pipeline](release-pipeline.html) | Workflow | Tests, the server/SDK parity gate, and idempotent publishing to PyPI |

## Layout

```text
visual/
├── index.html            generated hub with navigation
├── <slug>.html           generated page per diagram (heading, prose, embedded artifact)
├── assets/site.css       Catalyst design tokens, no framework
├── artifacts/*.html      the delivered, frozen archify artifacts
├── sources/*.json        typed archify IR — the editable source of truth
├── build-site.mjs        regenerates index.html and the diagram pages
├── check.sh              validates every source at showcase quality
├── deliver.sh            renders and commits every artifact
└── verify.sh             bounded desktop browser evidence per artifact
```

`artifacts/` is generated output. `sources/` is what you edit.

## Regenerating

```bash
# 1. edit visual/sources/<slug>.json
zsh visual/check.sh       # validate: schema, layout, routes, labels, readability
zsh visual/deliver.sh     # render + atomically commit each artifact
zsh visual/verify.sh      # desktop browser evidence at 1440x900 … 2048x1320
node visual/build-site.mjs  # regenerate the hub and the diagram pages
```

`check.sh` and `deliver.sh` hardcode the Archify install path. Adjust the `SKILL` variable at the
top of each if the skill lives somewhere else.

## The quality bar

Every diagram is held to Archify's `showcase` profile, which is nine artifact checks with zero
composition errors and zero warnings. All seven currently pass 9/9.

Browser containment is stricter than validation, because the reader is capped at a 930px diagram
column regardless of viewport size. Six of the seven also fit a 1440x900 viewport with no
scrolling:

| Diagram | Validation | Readability | 1440x900 containment |
|---|---|---|---|
| Runtime Architecture | 9/9 | pass | pass |
| SDK Flag Check | 9/9 | pass | pass |
| Toggle Propagation | 9/9 | pass | pass |
| Tenant Onboarding | 9/9 | pass | pass |
| SDK Client Lifecycle | 9/9 | pass | **fails by 16px** |
| Evaluation Data Flow | 9/9 | pass | pass |
| Release Pipeline | 9/9 | pass | pass |

The lifecycle overflows by 16px and that is a real geometric conflict rather than a tuning
miss. The lifecycle renderer reserves a `main` band, a shared middle band, and a `terminal`
outcome band, and refuses a `viewBox` shorter than about 634px. That fixes the panel height at
roughly 550px, which does not fit under the reader chrome plus cards inside 900px. Widening the
`viewBox` does not help, because the lifecycle lays states out on an anchored pitch and the extra
width becomes empty margin rather than a shorter panel. Shrinking it further drops the projected
node text below the 6px readability floor. The diagram pages therefore give the embedded artifact
a taller frame than a bare 900px viewport, so it still reads without an internal scrollbar in
practice.

## Editing a diagram

1. Change `visual/sources/<slug>.json`. The schema is the contract — read the matching file in the
   Archify skill's `schemas/` directory if you are unsure.
2. `zsh visual/check.sh` and fix only what the diagnostics name. The receipt gives you the exact
   `subject`, the measured `evidence`, and the supported fixes.
3. Re-run until it is clean, then `zsh visual/deliver.sh`.

Composition feedback is specific and worth reading in full. For example, an early draft of the
provisioning workflow failed because two edges leaving the same column shared a routing corridor;
the fix was to move a state rather than to add a route override.

## Reading an artifact

Each artifact is standalone and works offline. Inside one:

| Key | Action |
|-----|--------|
| `?` | open the factual diagram guide |
| `/` | find and focus a node by name |
| `R` | probe a directed route between two nodes |
| `L` | compare two semantic roles |
| `M` | open the overview radar |
| `P` or `[` `]` | play the guided chapters as a story |
| `F` | enter the presentation stage |
| `S` / `T` | cycle the visual style / toggle the theme |
| `E` | export PNG, SVG, video, or a share card |

Architecture nodes carry an `SRC n` badge that opens the exact file and line range, pinned to one
commit. Stable links restore state: `#focus=<id>`, `#relation=<id>`, `#route=<from>~<to>`,
`#lens=<kind>~<kind>`, and `#view=<view-id>`.
