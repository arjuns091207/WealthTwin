from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from app.api.portfolio import router as portfolio_router
from app.db.session import check_database_connection


app = FastAPI(
    title="WealthTwin API",
    version="0.1.0",
    description="Financial Digital Twin Platform",
)

app.include_router(portfolio_router)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "wealthtwin",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health/database")
def database_health_check():
    if not check_database_connection():
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        )

    return {
        "status": "healthy",
        "database": "postgresql",
        "query_test": "passed",
    }


@app.get("/")
def root():
    return {
        "message": "Welcome to WealthTwin API",
        "version": "0.1.0",
    }
