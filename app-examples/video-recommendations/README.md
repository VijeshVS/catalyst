# Reelwise — a Catalyst video recommendation demo

A small but complete video-recommendation platform. The FastAPI backend ranks a
fictional catalogue of titles; the light-themed frontend lets you change the
viewer and shows exactly why the rail looks the way it does. Five Catalyst flags
control the ranking, and every response carries the live decision, reason, rule
id and percentage bucket behind it.

The point of the demo is that the *ranking logic is ordinary product code*. The
flags decide which signals are allowed to run, who sees the premium shelf, and
which viewers get autoplay. Nothing restarts when a flag changes.

## What the flags control

All five live in the `Video Recommendations` project, `dev` environment.

| Flag | Kind | Dev configuration | What changes in the app |
|---|---|---|---|
| `recommendation-engine` | master switch | On, enabled to all users | Off serves the global trending rail instead of personalized ranking |
| `location-aware-ranking` | targeting rule | Rule: `country in [IN, US, GB, JP, DE, BR]` → true | Adds a location boost and a “Popular in …” signal |
| `genre-affinity-boost` | targeting rule | Rule: `favorite_genre exists` → true | Adds a genre boost and a “Matches your … history” signal |
| `premium-shelf` | targeting rule | Rule: `plan in [premium, family]` → true | Shows the early-access shelf; Free viewers never receive it |
| `autoplay-previews` | percentage rollout | 50%, no rules | Sticky per viewer: autoplay starts in the detail dialog for one bucket half and not the other |

The UI’s **Decision ledger** renders the server-side result for each flag —
including the raw reason code (`ENABLE_ALL_USERS`, `RULE_AND_ROLLOUT`,
`PERCENTAGE_ROLLOUT`, `DEFAULT_VALUE`, `KILL_SWITCH_ACTIVE`, …) and the viewer’s
bucket for the rollout.

## Architecture

```text
app-examples/video-recommendations/
├── app.py                 FastAPI routes, SDK client, static mount
├── catalog.py             22 fictional titles + country/genre/plan vocabularies
├── recommender.py         pure ranking: popularity + location + genre boosts
├── frontend/
│   ├── index.html         light, dependency-free UI
│   ├── styles.css         ivory / ink / antique-gold theme
│   └── app.js             audience controls, decision ledger, detail dialog
├── scripts/
│   └── provision_demo.py  idempotent account/project/flag/rule/key setup
├── requirements.txt
└── .env.example
```

Request flow:

1. The browser calls `GET /api/recommendations` with the simulated viewer.
2. `app.py` calls `client.refresh()` once. The SDK sends `If-None-Match`; an
   unchanged environment answers `304` and no snapshot body is transferred.
3. The SDK evaluates all five flags locally with
   `refresh_on_evaluate=False`, so five decisions cost one HTTP request.
4. `recommender.py` ranks locally using only the signals the flags allow.
5. The response includes the rail, the premium shelf, the autoplay decision and
   the full flag ledger.

The SDK fails closed. If Catalyst cannot be reached, every flag becomes false,
the API reports `snapshot.degraded`, and the UI shows the fallback banner and
trending rail instead of inventing a decision.

## Run

Run `scripts/provision_demo.py` once to create the demo resources and write the
gitignored `.env` (see [Provisioning](#provisioning)). A checkout that already
has a configured `.env` can skip straight to the commands below.

```bash
cd app-examples/video-recommendations

# Option A: uv (no activation needed)
uv venv
uv pip install -r requirements.txt
uv run uvicorn app:app --reload --port 8002

# Option B: plain venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app:app --reload --port 8002
```

Open <http://localhost:8002>. FastAPI’s interactive API docs are at
<http://localhost:8002/docs>, and the SDK/snapshot view is at
<http://localhost:8002/api/health>.

From the repository root, `make dev-video` runs the same app on port 8002.

## Demo walkthrough

1. **Baseline.** India + Sci-Fi + Premium. The rail is personalized, the premium
   shelf is visible, and the ledger shows the three rule flags on and autoplay
   decided by a 50% bucket.
2. **Drop the location signal.** Set Market to *Global*. The
   `location-aware-ranking` card flips to `DEFAULT_VALUE` and the “Popular in
   India” chips disappear from the cards.
3. **Drop the genre signal.** Set Most-watched genre to *Surprise me*. The
   `genre-affinity-boost` card flips off and the genre chips disappear.
4. **Hide the premium shelf.** Set Plan to *Free*. The shelf section disappears
   and `premium-shelf` reports `DEFAULT_VALUE`.
5. **Flip the rollout.** Press **Shuffle** until the viewer’s bucket moves to 50
   or above. `autoplay-previews` flips off without any rule changing; open a
   card and the simulated preview no longer auto-starts. Shuffling back restores
   it because the rollout is sticky per viewer ID.
6. **Pull the master switch.** In the Catalyst dashboard, turn the
   `recommendation-engine` kill switch off. The next request shows the
   “Trending now” fallback and a notice; turn it back on and the personalized
   rail returns. No app restart.

The viewer state is encoded in the URL, so a demo step can be bookmarked or
reopened on another screen.

## Provisioning

`scripts/provision_demo.py` is safe to re-run. It registers or signs in to a
demo account, finds or creates the `Reelwise` organization and
`Video Recommendations` project, creates the five flags, applies each dev state
and targeting rule, and mints one `reelwise-demo` SDK key.

```bash
REELWISE_PASSWORD='<demo account password>' \
  uv run --with httpx python scripts/provision_demo.py --write-env
```

The raw SDK key is returned by the API only once, at creation. The script prints
it and, with `--write-env`, writes it to the gitignored `.env`. `REELWISE_PASSWORD`
is required, because the script registers or signs in to a real account on the
deployment. Set `REELWISE_EMAIL`, `REELWISE_ORG`, or `CATALYST_HOST` to target a
different account or deployment.

> The local `.env` also records the demo dashboard login so the walkthrough can
> toggle flags in the hosted UI. Change that password after the demo and never
> commit `.env` or an SDK key.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Light-themed recommendation UI |
| `GET` | `/api/recommendations` | `user_id`, `country`, `genre`, `plan` → rail, shelf, ledger |
| `GET` | `/api/health` | SDK readiness, snapshot version, flag keys, counters |
| `GET` | `/docs` | FastAPI OpenAPI UI |

Example:

```bash
curl -s 'http://localhost:8002/api/recommendations?user_id=viewer-1&country=IN&genre=Sci-Fi&plan=premium' \
  | python3 -m json.tool
```

## Evaluation order

Catalyst evaluates kill switch → enable-all → rules by ascending priority →
percentage rollout. The demo deliberately has one flag at each interesting step:

- `recommendation-engine` uses enable-all, so the master switch is visible as a
  kill-switch demonstration.
- `location-aware-ranking`, `genre-affinity-boost`, and `premium-shelf` use
  rules, so attribute targeting is visible.
- `autoplay-previews` uses a percentage, so sticky bucketing is visible.

The backend never re-implements those decisions. It reads `EvaluationResult`
values from `sdk-catalyst`, which mirrors the server evaluator; the SDK and API
share the same Murmur3 bucketing, so the bucket shown in the UI is the bucket
that decided the flag.
