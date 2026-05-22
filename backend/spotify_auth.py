import os
import httpx
from fastapi import HTTPException

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
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