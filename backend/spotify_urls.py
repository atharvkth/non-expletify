"""
Parsing utilities for Spotify playlist references.

Spotify hands users playlist links in a few different shapes depending
on where the "Share" menu was invoked. This module normalizes all of
them down to a single 22-character base62 playlist ID, and rejects
anything that doesn't fit.

Supported inputs:
    https://open.spotify.com/playlist/<id>
    https://open.spotify.com/playlist/<id>?si=...
    https://open.spotify.com/intl-<lang>/playlist/<id>
    spotify:playlist:<id>
    <id>                                 (bare ID, allowed for convenience)
"""

import re


# Spotify IDs are 22 chars of base62: digits + upper + lower.
# The pattern matches either "playlist/<id>" (URL form) or
# "playlist:<id>" (URI form), with the ID captured.
_PLAYLIST_RE = re.compile(r"playlist[/:]([A-Za-z0-9]{22})")

# Bare-ID convenience pattern: exactly 22 base62 chars, nothing else.
_BARE_ID_RE = re.compile(r"^[A-Za-z0-9]{22}$")


class InvalidPlaylistReference(ValueError):
    """Raised when input doesn't contain a recognizable playlist ID."""


def parse_playlist_id(raw: str) -> str:
    """
    Extract the playlist ID from any supported Spotify reference shape.

    Raises InvalidPlaylistReference if the input doesn't match.
    """
    if not isinstance(raw, str):
        raise InvalidPlaylistReference("Input must be a string.")

    candidate = raw.strip()
    if not candidate:
        raise InvalidPlaylistReference("Input is empty.")

    # Bare ID — accept as-is. Useful for power users and for tests.
    if _BARE_ID_RE.match(candidate):
        return candidate

    # URL or URI form — find the ID after the "playlist" marker.
    match = _PLAYLIST_RE.search(candidate)
    if match:
        return match.group(1)

    raise InvalidPlaylistReference(
        "That doesn't look like a Spotify playlist link. "
        "Expected a URL like https://open.spotify.com/playlist/... "
        "or a URI like spotify:playlist:..."
    )