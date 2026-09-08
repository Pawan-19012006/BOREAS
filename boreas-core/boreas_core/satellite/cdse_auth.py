"""OAuth2 client-credentials token fetch for the Copernicus Data Space
Ecosystem (CDSE), used by sentinel_hub.py to authorize real Sentinel-1/2
imagery requests.

Endpoint and flow verified against CDSE's own current documentation this
session (not guessed):
- Token endpoint: https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token
  (documentation.dataspace.copernicus.eu/APIs/Token.html)
- grant_type=client_credentials with client_id/client_secret, confirmed via
  documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html
  (this is the OAuth client created via the Sentinel Hub dashboard's "User
  Settings", not the same as a personal CDSE login).
"""

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_CLIENT_ID_ENV = "CDSE_CLIENT_ID"
CDSE_CLIENT_SECRET_ENV = "CDSE_CLIENT_SECRET"

# (token, expires_at_monotonic) -- process-lifetime, in-memory. Refreshed a
# safety margin before real expiry so an in-flight request never gets handed
# a token that expires mid-call.
_TOKEN_SAFETY_MARGIN_SECONDS = 30.0
_cached_token: tuple[str, float] | None = None


class CdseAuthError(Exception):
    """Raised when a CDSE token cannot be obtained -- missing config, bad
    credentials, or a network/HTTP failure. Callers should catch this and
    degrade to an "unavailable" response, never propagate it as a 500.

    Carries the raw upstream status/body (when there was an HTTP response
    at all) as `upstream_status`/`upstream_body` so a caller can distinguish
    "bad credentials" (e.g. HTTP 401, `invalid_client`) from "wrong OAuth
    scope" or a network failure, rather than only getting a flattened
    string message.
    """

    def __init__(self, message: str, *, upstream_status: int | None = None, upstream_body: str | None = None):
        super().__init__(message)
        self.upstream_status = upstream_status
        self.upstream_body = upstream_body

    def debug_dict(self) -> dict:
        return {
            "message": str(self),
            "upstream_status": self.upstream_status,
            "upstream_body": self.upstream_body,
        }


def get_cdse_token(*, timeout_s: float = 10.0) -> str:
    global _cached_token

    if _cached_token is not None:
        token, expires_at = _cached_token
        if time.monotonic() < expires_at:
            return token

    client_id = os.environ.get(CDSE_CLIENT_ID_ENV)
    client_secret = os.environ.get(CDSE_CLIENT_SECRET_ENV)
    if not client_id or not client_secret:
        raise CdseAuthError(f"{CDSE_CLIENT_ID_ENV} / {CDSE_CLIENT_SECRET_ENV} not configured")

    try:
        response = httpx.post(
            CDSE_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=timeout_s,
        )
    except httpx.HTTPError as exc:
        logger.warning("CDSE token request failed (network): %s", exc)
        raise CdseAuthError(f"CDSE token request failed: {exc}") from exc

    if response.status_code != 200:
        # Not truncated -- CDSE/Keycloak error bodies are short JSON
        # ({"error": "invalid_client", "error_description": "..."}) and the
        # whole point of this exception is to show the real cause.
        logger.warning("CDSE token request returned HTTP %s: %s", response.status_code, response.text)
        raise CdseAuthError(
            f"CDSE token request returned HTTP {response.status_code}: {response.text}",
            upstream_status=response.status_code,
            upstream_body=response.text,
        )

    data = response.json()
    token = data.get("access_token")
    expires_in = data.get("expires_in", 300)
    if not token:
        logger.warning("CDSE token response had no access_token field: %s", response.text)
        raise CdseAuthError(
            "CDSE token response had no access_token field",
            upstream_status=response.status_code,
            upstream_body=response.text,
        )

    _cached_token = (token, time.monotonic() + max(expires_in - _TOKEN_SAFETY_MARGIN_SECONDS, 5.0))
    return token


def _reset_cache_for_tests() -> None:
    global _cached_token
    _cached_token = None
