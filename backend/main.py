import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from spotify_urls import parse_playlist_id, InvalidPlaylistReference
from spotify_auth import (
    exchange_code_for_tokens,
    refresh_access_token,
    spotify_get,
    spotify_get_all,
)

load_dotenv()

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


def get_access_token(session_id: str) -> str:
    """Pull the access token for a session, or 401 if there isn't one."""
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="No session")
    return session["access_token"]


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


@app.get("/me")
async def me(session_id: str):
    access_token = get_access_token(session_id)
    # print(f"[/me] token starts with: {access_token[:12]}...")

    try:
        profile = await spotify_get(access_token, "/me")
    except HTTPException as e:
        # print(f"[/me] first call raised {e.status_code}; trying refresh")
        if e.status_code == 401:
            await refresh_with_session(session_id)
            access_token = get_access_token(session_id)
            profile = await spotify_get(access_token, "/me")
        else:
            raise

    # print(f"[/me] profile = {profile!r}")

    if profile is None:
        raise HTTPException(status_code=502, detail="Empty response from Spotify /me")

    return {
        "id": profile["id"],
        "display_name": profile.get("display_name"),
        "image_url": (profile.get("images") or [{}])[0].get("url"),
    }


async def refresh_with_session(session_id: str):
    """Refresh the access token for a session in place."""
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="No session")
    new_tokens = await refresh_access_token(session["refresh_token"])
    SESSIONS[session_id] = {**session, **new_tokens}


@app.get("/callback")
async def callback_page():
    # Spotify redirects here after consent. We just serve the page that
    # reads the ?code=... out of the URL and posts it to /auth/exchange.
    return FileResponse(os.path.join(FRONTEND_DIR, "callback.html"))


class PlaylistFetchRequest(BaseModel):
    session_id: str
    playlist_ref: str  # raw URL, URI, or ID as the user pasted it


@app.post("/playlist/fetch")
async def fetch_playlist(req: PlaylistFetchRequest):
    try:
        playlist_id = parse_playlist_id(req.playlist_ref)
    except InvalidPlaylistReference as e:
        raise HTTPException(status_code=400, detail=str(e))

    access_token = get_access_token(req.session_id)

    try:
        meta = await spotify_get(
            access_token,
            f"/playlists/{playlist_id}",
            # `tracks(total)` → `items(total)` per the field rename
            params={"fields": "name,owner(display_name),items(total)"},
        )
        raw_items = await spotify_get_all(
            access_token,
            # /tracks → /items
            f"/playlists/{playlist_id}/items",
            params={
                # The wrapper field is now `item`, not `track`
                "fields": (
                    "items(item(id,name,uri,duration_ms,explicit,"
                    "external_ids,artists(id,name),album(id,name))),"
                    "next"
                ),
                "limit": 100,
            },
        )
    except HTTPException as e:
        if e.status_code == 401:
            await refresh_with_session(req.session_id)
            access_token = get_access_token(req.session_id)
            meta = await spotify_get(
                access_token,
                f"/playlists/{playlist_id}",
                params={"fields": "name,owner(display_name),items(total)"},
            )
            raw_items = await spotify_get_all(
                access_token,
                f"/playlists/{playlist_id}/items",
                params={
                    "fields": (
                        "items(item(id,name,uri,duration_ms,explicit,"
                        "external_ids,artists(id,name),album(id,name))),"
                        "next"
                    ),
                    "limit": 100,
                },
            )
        else:
            raise

    tracks = []
    for entry in raw_items:
        # Spotify wraps each track in {"item": {...}} now (was "track").
        # Can still be null for local files or region-restricted content.
        t = entry.get("item")
        if not t or not t.get("id"):
            continue
        tracks.append({
            "id": t["id"],
            "uri": t["uri"],
            "name": t["name"],
            "artists": [{"id": a["id"], "name": a["name"]} for a in t["artists"]],
            "album": {"id": t["album"]["id"], "name": t["album"]["name"]},
            "duration_ms": t["duration_ms"],
            "explicit": t["explicit"],
            "isrc": (t.get("external_ids") or {}).get("isrc"),
        })

    explicit_count = sum(1 for t in tracks if t["explicit"])

    return {
        "playlist": {
            "id": playlist_id,
            "name": meta["name"],
            "owner": meta["owner"]["display_name"],
            "total_tracks": meta["items"]["total"],  # was meta["tracks"]["total"]
        },
        "tracks": tracks,
        "explicit_count": explicit_count,
    }


# ---------------------------------------------------------------------------
# Static frontend mount. KEEP THIS LAST. html=True means "/" serves
# index.html, and visiting /foo serves foo.html if it exists.
# ---------------------------------------------------------------------------
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")