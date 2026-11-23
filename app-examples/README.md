# Catalyst Python application examples

Two small applications demonstrate a Python service checking Catalyst flags
before exposing a feature:

| Example | What it does | Flag |
|---|---|---|
| [App 1](app-1/README.md) | FastAPI shop checkout switches between standard and express checkout | `express-checkout` |
| [App 2](app-2/README.md) | Inventory CLI optionally includes low-stock alerts | `low-stock-alerts` |

## Setup both apps

1. In the Catalyst dashboard, create a project and use its `dev` environment.
2. Create the flag listed for the app you want to run. New flags are off by
   default; turn on **Enable to all users** to see the new behavior.
3. Create a `dev` SDK key from the project's **API Keys** tab.
4. In the app's folder, copy `.env.example` to `.env` and put the project settings
   in `.env`:

   ```bash
   cp .env.example .env
   ```

   Edit `CATALYST_SDK_KEY` and `CATALYST_PROJECT_ID`; set `CATALYST_HOST` in
   `.env` only when using a locally running Catalyst API.

Each check reads the current flag configuration through the SDK, so dashboard
changes take effect without restarting the FastAPI app. The SDK checks on each
evaluation with a conditional request, not on a timer. The CLI reads the
current value each time it runs. If a read fails, the SDK fails closed and the
new feature stays off.
