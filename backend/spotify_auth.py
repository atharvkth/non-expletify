import os
import httpx
from fastapi import HTTPException

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
REDIRECT_URI = os.getenv("REDIRECT_URI")

async def exchange_code_for_tokens(code: str, code_verifier: str) -> dict:
    """
    Exchange the authorization code + PKCE verifier for tokens.
    This is the step Spotify uses to verify we're the same app
    that started the auth flow (by checking the verifier hashes
    to the challenge it saw earlier).
    """
    print(f"DEBUG client_id: {repr(CLIENT_ID)}")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": code_verifier,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            SPOTIFY_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Token exchange failed: {response.text}",
        )

    return response.json()
    # Returns: { access_token, token_type, scope, expires_in, refresh_token }


async def refresh_access_token(refresh_token: str) -> dict:
    """
    Access tokens expire after 1 hour. Use the refresh token
    (which is long-lived) to get a new access token without
    making the user log in again.
    """
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            SPOTIFY_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Refresh failed")

    return response.json()


async def spotify_get(access_token: str, path: str, params: dict | None = None) -> dict:
    """
    Authenticated GET against the Spotify Web API.
    `path` is the part after /v1, e.g. "/me" or "/playlists/{id}".
    Caller is responsible for token freshness — refresh upstream if 401.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SPOTIFY_API_BASE}{path}",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )

    if response.status_code == 401:
        # Token expired or revoked. Surface this distinctly so the
        # route layer can decide whether to refresh and retry.
        raise HTTPException(status_code=401, detail="Spotify token invalid")

    if response.status_code == 429:
        # Spotify is rate-limiting us. Retry-After tells us how long.
        retry_after = response.headers.get("Retry-After", "1")
        raise HTTPException(
            status_code=429,
            detail=f"Rate limited; retry after {retry_after}s",
        )

    if not response.is_success:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Spotify API error: {response.text}",
        )

    return response.json()
