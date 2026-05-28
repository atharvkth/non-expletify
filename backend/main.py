import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from spotify_auth import exchange_code_for_tokens, refresh_access_token

app = FastAPI()

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

# CORS is no longer strictly required now that the frontend is served
# from the same origin as the backend, but it's harmless to leave in
# while developing. Lock origins down before deploying.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory token store for dev only. Dies on restart, doesn't survive
# multiple workers. Replace with Redis or signed HttpOnly cookies before
# any real deployment. Never put raw tokens in localStorage.
SESSIONS: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# API + auth routes. These MUST be defined BEFORE the StaticFiles mount at
# the bottom. A catch-all mount at "/" swallows anything defined after it,
# so any route below the mount would silently 404.
# ---------------------------------------------------------------------------

class TokenExchangeRequest(BaseModel):
    code: str
    code_verifier: str
    session_id: str  # client-generated UUID identifying this user session


@app.post("/auth/exchange")
async def exchange(req: TokenExchangeRequest):
    tokens = await exchange_code_for_tokens(req.code, req.code_verifier)
    SESSIONS[req.session_id] = tokens
    return {"ok": True, "expires_in": tokens["expires_in"]}


@app.get("/auth/status")
async def status(session_id: str):
    return {"logged_in": session_id in SESSIONS}


@app.post("/auth/refresh")
async def refresh(session_id: str):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=401, detail="No session")
    new_tokens = await refresh_access_token(SESSIONS[session_id]["refresh_token"])
    # Spotify sometimes returns a new refresh_token, sometimes not.
    # Preserve the old one if it's absent from the response.
    SESSIONS[session_id] = {**SESSIONS[session_id], **new_tokens}
    return {"ok": True}


@app.get("/callback")
async def callback_page():
    # Spotify redirects here after consent. We just serve the page that
    # reads the ?code=... out of the URL and posts it to /auth/exchange.
    return FileResponse(os.path.join(FRONTEND_DIR, "callback.html"))


# ---------------------------------------------------------------------------
# Static frontend mount. KEEP THIS LAST. html=True means "/" serves
# index.html, and visiting /foo serves foo.html if it exists.
# ---------------------------------------------------------------------------
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")