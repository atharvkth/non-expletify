import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from spotify_auth import exchange_code_for_tokens, refresh_access_token

app = FastAPI()

@app.get("/callback")
async def callback_page():
    # Serve the frontend's callback.html. Adjust the path to wherever
    # your callback.html actually lives relative to where you run uvicorn.
    return FileResponse("../frontend/callback.html")

# CORS so your frontend (on a different port) can call your backend.
# In production, lock origins down to your real domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory token store for dev. Replace with Redis or signed cookies
# for anything real. Keyed by a session ID the frontend holds.
SESSIONS: dict[str, dict] = {}


class TokenExchangeRequest(BaseModel):
    code: str
    code_verifier: str
    session_id: str  # client-generated UUID, identifies this user session


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
    # Spotify sometimes returns a new refresh_token, sometimes doesn't.
    # Preserve the old one if not returned.
    SESSIONS[req.session_id] = {
        **SESSIONS[session_id],
        **new_tokens,
    }
    return {"ok": True}