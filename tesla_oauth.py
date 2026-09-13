"""Tesla Fleet OAuth: refresh access token and persist the rotated pair.

Tesla third-party tokens:
- access_token: short lived (hours). Fleet calls use Bearer access.
- refresh_token: single-use, valid ~3 months if unused. Each refresh
  returns a NEW refresh token that must be saved immediately.
- Last used refresh stays valid up to 24h if the save failed.

Auth host must be fleet-auth (not fleet-api). Client id is the owner
app bound to danielvegac.github.io: 523a361f-...
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import config

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

TESLA_AUTH_URL = "https://fleet-auth.prd.vn.cloud.tesla.com/oauth2/v3/token"
DEFAULT_CLIENT_ID = "523a361f-12e3-4f22-a95e-b71348948b51"
FORBIDDEN_CLIENT_ID = "8176c514-862e-4fc2-948c-0e4e7d9f7310"


def _client_id() -> str:
    raw = (os.getenv("TESLA_CLIENT_ID") or getattr(config, "TESLA_CLIENT_ID", "") or DEFAULT_CLIENT_ID).strip()
    if raw == FORBIDDEN_CLIENT_ID:
        raise RuntimeError(
            "TESLA_CLIENT_ID 8176c514 is bound to a different domain. Use 523a361f."
        )
    return raw or DEFAULT_CLIENT_ID


def env_path() -> Path:
    return Path(os.getenv("TESLA_ENV_FILE") or Path(__file__).resolve().parent / ".env")


def upsert_env(path: Path, updates: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    seen = set()
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    text = "\n".join(out).rstrip() + "\n"
    path.write_text(text)


def apply_tokens(access: str, refresh: str) -> None:
    os.environ["TESLA_ACCESS_TOKEN"] = access
    os.environ["TESLA_REFRESH_TOKEN"] = refresh
    config.TESLA_ACCESS_TOKEN = access
    config.TESLA_REFRESH_TOKEN = refresh


def refresh_tokens(refresh_token: Optional[str] = None) -> Tuple[str, str, int]:
    """Exchange refresh token. Returns (access, new_refresh, expires_in)."""
    if httpx is None:
        raise RuntimeError("httpx is not installed")
    token = (refresh_token or config.TESLA_REFRESH_TOKEN or os.getenv("TESLA_REFRESH_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("TESLA_REFRESH_TOKEN is empty — cannot auto-refresh")

    client_id = _client_id()
    verify = config.TESLA_HTTP_VERIFY
    resp = httpx.post(
        TESLA_AUTH_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
        verify=verify,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Tesla token refresh failed {resp.status_code}: {resp.text[:400]}"
        )
    payload = resp.json()
    access = (payload.get("access_token") or "").strip()
    new_refresh = (payload.get("refresh_token") or token).strip()
    expires_in = int(payload.get("expires_in") or 0)
    if not access:
        raise RuntimeError(f"Tesla refresh response missing access_token: {payload}")
    return access, new_refresh, expires_in


def refresh_and_persist(refresh_token: Optional[str] = None) -> Tuple[str, str, int]:
    access, new_refresh, expires_in = refresh_tokens(refresh_token)
    apply_tokens(access, new_refresh)
    upsert_env(
        env_path(),
        {
            "TESLA_ACCESS_TOKEN": access,
            "TESLA_REFRESH_TOKEN": new_refresh,
        },
    )
    print(
        f"[oauth] refreshed access len={len(access)} "
        f"refresh_rotated={new_refresh != (refresh_token or '')} "
        f"expires_in={expires_in}s"
    )
    return access, new_refresh, expires_in


if __name__ == "__main__":
    refresh_and_persist()
    print("ok: wrote new access + refresh to .env")
