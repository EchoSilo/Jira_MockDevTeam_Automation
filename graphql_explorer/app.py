"""
Jira GraphQL Explorer — a small prototype for poking at Jira's (mostly undocumented)
GraphQL endpoints with the credentials already configured in the project .env.

Run:
    pip install -r graphql_explorer/requirements.txt
    python -m uvicorn graphql_explorer.app:app --reload --port 8765

Then open http://localhost:8765/ for the GraphiQL playground.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

# Load .env from project root (parent of this file's directory)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

JIRA_URL = (os.getenv("JIRA_URL") or "").rstrip("/")
JIRA_EMAIL = os.getenv("JIRA_EMAIL") or ""
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN") or ""

if not (JIRA_URL and JIRA_EMAIL and JIRA_API_TOKEN):
    # Don't crash at import — let the endpoints report the problem so the UI still loads.
    pass


# Candidate Jira GraphQL endpoints. Jira's GraphQL surface is poorly documented,
# so we list every URL that has been observed in the wild and let the probe tell
# us which ones respond for this tenant.
def candidate_endpoints() -> list[dict[str, str]]:
    base = JIRA_URL or "https://example.atlassian.net"
    return [
        {
            "id": "gateway",
            "label": "Cloud Gateway (/gateway/api/graphql)",
            "url": f"{base}/gateway/api/graphql",
            "notes": "Primary internal Cloud GraphQL gateway. Aggregates Jira/Confluence/Compass.",
        },
        {
            "id": "jira-gateway",
            "label": "Jira-scoped Gateway (/gateway/api/jira/graphql)",
            "url": f"{base}/gateway/api/jira/graphql",
            "notes": "Jira-prefixed variant occasionally observed.",
        },
        {
            "id": "jsw",
            "label": "Jira Software (/jsw/graphql)",
            "url": f"{base}/jsw/graphql",
            "notes": "Jira Software internal GraphQL (boards/sprints).",
        },
        {
            "id": "rest-graphql",
            "label": "REST GraphQL (/rest/graphql/1/)",
            "url": f"{base}/rest/graphql/1/",
            "notes": "Legacy REST-style GraphQL endpoint (Server/DC era).",
        },
        {
            "id": "public",
            "label": "Public Atlassian (api.atlassian.com/graphql)",
            "url": "https://api.atlassian.com/graphql",
            "notes": "Public Atlassian GraphQL. Requires OAuth 2.0 — Basic auth will 401.",
        },
    ]


def basic_auth_header() -> str:
    token = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    return f"Basic {token}"


def default_headers() -> dict[str, str]:
    return {
        "Authorization": basic_auth_header(),
        "Accept": "application/json",
        "Content-Type": "application/json",
        # Some Cloud endpoints reject requests without an Atlassian client identifier.
        "X-ExperimentalApi": "opt-in",
        "User-Agent": "jira-graphql-explorer/0.1",
    }


app = FastAPI(title="Jira GraphQL Explorer", version="0.1.0")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/config")
def config() -> dict[str, Any]:
    return {
        "jira_url": JIRA_URL or None,
        "jira_email_set": bool(JIRA_EMAIL),
        "jira_token_set": bool(JIRA_API_TOKEN),
        "endpoints": candidate_endpoints(),
    }


@app.get("/api/probe")
async def probe() -> dict[str, Any]:
    """Send a minimal introspection query to every candidate endpoint and report results."""
    if not (JIRA_URL and JIRA_EMAIL and JIRA_API_TOKEN):
        raise HTTPException(
            status_code=500,
            detail="JIRA_URL, JIRA_EMAIL, and JIRA_API_TOKEN must be set in .env",
        )

    query = {"query": "{ __typename }"}
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for ep in candidate_endpoints():
            entry: dict[str, Any] = {
                "id": ep["id"],
                "label": ep["label"],
                "url": ep["url"],
                "notes": ep["notes"],
            }
            try:
                r = await client.post(ep["url"], headers=default_headers(), json=query)
                entry["status"] = r.status_code
                ct = r.headers.get("content-type", "")
                entry["content_type"] = ct
                body_snippet = r.text[:400]
                entry["body_snippet"] = body_snippet
                parsed: Any = None
                if "application/json" in ct:
                    try:
                        parsed = r.json()
                    except ValueError:
                        parsed = None
                entry["responded_with_json"] = parsed is not None
                entry["has_graphql_data"] = bool(
                    isinstance(parsed, dict) and ("data" in parsed or "errors" in parsed)
                )
                entry["typename"] = (
                    parsed.get("data", {}).get("__typename")
                    if isinstance(parsed, dict) and isinstance(parsed.get("data"), dict)
                    else None
                )
                entry["verdict"] = _classify(entry)
            except httpx.RequestError as e:
                entry["status"] = None
                entry["error"] = f"{type(e).__name__}: {e}"
                entry["verdict"] = "unreachable"
            results.append(entry)

    return {"results": results}


def _classify(entry: dict[str, Any]) -> str:
    status = entry.get("status")
    if status is None:
        return "unreachable"
    if entry.get("typename"):
        return "graphql-working"
    if entry.get("has_graphql_data"):
        return "graphql-responds-with-errors"
    if status in (401, 403):
        return "auth-required"
    if status == 404:
        return "not-found"
    if status == 405:
        return "method-not-allowed"
    if 200 <= status < 300:
        return "responded-but-not-graphql"
    return f"http-{status}"


@app.post("/graphql")
async def proxy(
    request: Request,
    endpoint: str = Query("gateway", description="Endpoint id from /api/config"),
) -> JSONResponse:
    """Proxy a GraphQL request to the selected Jira endpoint.

    The proxy intentionally forwards anything the client sends as JSON, including
    `query`, `variables`, and `operationName` — which is exactly what GraphiQL emits.
    """
    if not (JIRA_URL and JIRA_EMAIL and JIRA_API_TOKEN):
        raise HTTPException(
            status_code=500,
            detail="JIRA_URL, JIRA_EMAIL, and JIRA_API_TOKEN must be set in .env",
        )

    target = next((e for e in candidate_endpoints() if e["id"] == endpoint), None)
    if target is None:
        raise HTTPException(status_code=400, detail=f"Unknown endpoint id: {endpoint}")

    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Request body must be JSON")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            r = await client.post(target["url"], headers=default_headers(), json=payload)
        except httpx.RequestError as e:
            return JSONResponse(
                status_code=502,
                content={
                    "errors": [
                        {
                            "message": f"Upstream request failed: {type(e).__name__}: {e}",
                            "extensions": {"endpoint": target["url"]},
                        }
                    ]
                },
            )

    # Try to surface the upstream response as JSON; fall back to wrapping the text.
    try:
        body = r.json()
    except ValueError:
        body = {
            "errors": [
                {
                    "message": "Upstream did not return JSON",
                    "extensions": {
                        "status": r.status_code,
                        "content_type": r.headers.get("content-type"),
                        "body_snippet": r.text[:500],
                    },
                }
            ]
        }

    return JSONResponse(status_code=r.status_code, content=body)
