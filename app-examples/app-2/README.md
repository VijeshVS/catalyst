# App 2: Inventory report CLI

A command-line inventory report that always displays stock levels. The
`low-stock-alerts` flag gates the newer alert feature: when enabled, items at or
below their reorder point are called out for the store operator. This is a
separate, non-web example of using the same Catalyst Python SDK.

## Run

From this directory, configure the SDK as shown in [`../README.md`](../README.md),
then run:

```bash
cp .env.example .env
# Edit .env with your SDK key and project ID.
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py --user-id warehouse-operator --plan pro
```

Enable **Enable to all users** for `low-stock-alerts` in the dashboard and run
the command again. The inventory is unchanged, but the report now includes
reorder alerts. Try a different user or plan if you configure a targeting rule
for the flag.
