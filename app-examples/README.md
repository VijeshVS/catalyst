# Catalyst Python application examples

A small application demonstrates a Python service checking Catalyst flags
before exposing a feature:

| Example | What it does | Flags |
|---|---|---|
| [Reelwise](video-recommendations/README.md) | FastAPI video-recommendation demo with a dependency-free frontend and a decision ledger | `recommendation-engine`, `location-aware-ranking`, `genre-affinity-boost`, `premium-shelf`, `autoplay-previews` |

## Setup

1. In the Catalyst dashboard, create a project and use its `dev` environment.
2. Create the flags listed for the example you want to run. New flags are off by
   default; the Reelwise provisioning script applies the demo configuration for
   you.
3. Create a `dev` SDK key from the project's **API Keys** tab.
4. In the app's folder, copy `.env.example` to `.env` and put the project settings
   in `.env`:

   ```bash
   cp .env.example .env
   ```

   Edit `CATALYST_SDK_KEY` and `CATALYST_PROJECT_ID`; set `CATALYST_HOST` in
   `.env` only when using a locally running Catalyst API.

Each check reads the current flag configuration through the SDK, so dashboard
changes take effect without restarting the service. Reelwise refreshes once per
request with a conditional request, then evaluates locally. If a read fails, the
SDK fails closed and the new feature stays off.
