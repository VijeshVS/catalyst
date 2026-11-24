# App 1: Shop checkout API

A small FastAPI application with a real checkout-preview endpoint. The
`express-checkout` flag controls whether a customer gets the express flow or the
standard payment-details flow. The response includes the flag decision and
reason, which makes the example useful to walk through during a presentation.

## Run

From this directory, configure the SDK as shown in [`../README.md`](../README.md),
then run:

```bash
cp .env.example .env
# Edit .env with your SDK key and project ID.
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8001
```

Open <http://localhost:8001/docs> to try the endpoint, or send a request:

```bash
curl -X POST http://localhost:8001/checkout \
  -H 'content-type: application/json' \
  -H 'x-user-id: customer-123' \
  -H 'x-plan: pro' \
  -d '{"items": [{"name": "Coffee", "price": 4.5, "quantity": 2}]}'
```

Turn `express-checkout` on or off in the dashboard and repeat the request. The
response's `checkout_flow` and `message` show which implementation the flag
selected. The flag is evaluated per request, so no app restart is needed.
