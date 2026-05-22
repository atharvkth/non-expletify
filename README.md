# Non-Expletify

Takes a Spotify playlist link and builds an identical playlist using the non-explicit versions of each track — for the car ride with family, coworkers, or anyone you'd rather not subject to your full library.

## Status

Early scaffolding. OAuth + PKCE flow against the Spotify Web API is working end-to-end; playlist fetching and the explicit-to-clean matching pipeline are next.

## How it will work

Given a public Spotify playlist URL, the app will:

1. Authenticate the user against their own Spotify account (so the cleaned playlist lands in their library).
2. Fetch the source playlist's tracks.
3. For each track marked `explicit`, search for a non-explicit counterpart — same artist, matching title, comparable duration. Radio edits are accepted as substitutes.
4. Show the user the proposed mapping, including any tracks where no clean version could be found, before anything is created.
5. On confirmation, create a new playlist in the user's account named `<Original> (Clean)`, with a description listing any skipped tracks.

Tracks without a clean version are surfaced rather than silently dropped — the user decides whether to skip them, keep the explicit version, or search manually.

## Stack

- **Backend:** Python, FastAPI, httpx
- **Frontend:** Plain HTML/JS (React wrapper likely later)
- **Auth:** Spotify Authorization Code Flow with PKCE

PKCE is used instead of the classic client-secret flow so there's no long-lived secret to manage or leak.

## Running locally

### Prerequisites

- Python 3.10+
- A Spotify developer app registered at https://developer.spotify.com/dashboard with redirect URI `http://127.0.0.1:8000/callback`

### Setup

```bash
git clone https://github.com/<your-username>/non-expletify.git
cd non-expletify
pip install -r requirements.txt
```

Create `backend/.env`:

```
SPOTIFY_CLIENT_ID=your_client_id_here
REDIRECT_URI=http://127.0.0.1:8000/callback
FRONTEND_URL=http://127.0.0.1:5500
```

### Run

```bash
# Backend
cd backend
uvicorn main:app --reload --host 127.0.0.1 --port 8000

# Frontend (separate terminal)
cd frontend
python -m http.server 5500 --bind 127.0.0.1
```

Open `http://127.0.0.1:5500/index.html` and click **Log in with Spotify**.

## OAuth scopes requested

- `playlist-read-private`
- `playlist-read-collaborative`
- `playlist-modify-public`
- `playlist-modify-private`

Nothing beyond what's needed to read source playlists and create the cleaned copy.

## Roadmap

- [x] OAuth + PKCE scaffold
- [ ] Fetch source playlist tracks
- [ ] Matching pipeline: album sweep → artist search → ISRC neighborhood → graceful skip
- [ ] Results review UI before playlist creation
- [ ] Create cleaned playlist in user's account
- [ ] Rate limit handling and retry logic
- [ ] Deploy

## Notes

Dev token storage is in-memory and resets when the backend restarts — fine for local development, replaced with Redis or signed cookies before any real deployment. Tokens are never exposed to `localStorage`.

This project uses the Spotify Web API under Spotify's developer terms. It is not affiliated with or endorsed by Spotify.
