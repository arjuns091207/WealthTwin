 # WealthTwin API

WealthTwin is a FastAPI backend for portfolio valuation and stress testing.

## Running the backend

Run from the backend directory:

```powershell
python -m uvicorn app.main:app --reload
```

## Endpoints

### GET /health
Returns the service health status.

### POST /api/v1/portfolio/valuation
Calculates market values for portfolio positions.

### POST /api/v1/scenarios/stress
Calculates position-level and portfolio-level changes under percentage shocks.

### POST /api/v1/scenarios/report
Returns scenario stress results and a SHA-256 input fingerprint. Equivalent decimal formatting is normalized, and position order is preserved.

The fingerprint does not store historical reports or verify market-data accuracy.

## Interactive documentation

Open /docs in the running API.
Open /openapi.json for the API specification.

## Tests

```powershell
python -m pytest .\tests -v
```

Invalid requests return HTTP 422.
