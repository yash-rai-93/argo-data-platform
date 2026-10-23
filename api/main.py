"""ARGO Product Intelligence API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import activity, customers, intelligence, metrics, predict


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Warm the XGBoost model and SHAP explainer before serving traffic.

    A missing or stale model artifact must not stop the process from booting,
    so a failed warm-up is logged and deferred to the first request.
    """
    try:
        predict.warm_cache()
        print("Churn model and SHAP explainer warmed.")
    except Exception as error:
        print(f"Model warm-up skipped: {error}")
    yield


app = FastAPI(title="ARGO Product Intelligence API", lifespan=lifespan)

# Every endpoint is public, read-only, and derived from public GitHub Archive
# data, so any origin may call it -- including whatever preview domain Vercel
# mints per deployment, which is why the list is not enumerated.
#
# allow_credentials stays False deliberately. The client sends no cookies and
# no Authorization header, and the API reads neither. Setting it True while
# allow_origins is "*" makes Starlette echo the caller's own origin back
# instead of "*", which would let any site on the internet make credentialed
# requests -- a strictly weaker posture bought for no functional gain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(activity.router)
app.include_router(metrics.router)
app.include_router(intelligence.router)
app.include_router(predict.router)
app.include_router(customers.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
