
from fastapi import FastAPI
from datetime import datetime, timezone

app = FastAPI(
    title="WealthTwin API",
    version="0.1.0",
    description="Financial Digital Twin Platform"
)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "wealthtwin",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/")
def root():
    return {
        "message": "Welcome to WealthTwin API",
        "version": "0.1.0"
    }