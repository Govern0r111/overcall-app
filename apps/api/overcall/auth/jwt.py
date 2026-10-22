from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
import jwt
from jwt import PyJWK

from ..config import Settings

JWKS_CACHE_SECONDS = 3_600


class InvalidSupabaseToken(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedIdentity:
    user_id: UUID
    email: str | None


class SupabaseJWTVerifier:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        cache_seconds: int = JWKS_CACHE_SECONDS,
        clock=time.monotonic,
    ) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=5.0)
        self._owns_client = client is None
        self.cache_seconds = cache_seconds
        self.clock = clock
        self._keys: dict[str, dict[str, Any]] = {}
        self._expires_at = 0.0
        self._refresh_lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def verify(self, token: str) -> VerifiedIdentity:
        issuer = self._issuer
        if issuer is None:
            raise InvalidSupabaseToken("Supabase URL is not configured")
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            allowed_algorithms = self.settings.allowed_supabase_jwt_algorithms
            if algorithm not in allowed_algorithms:
                raise InvalidSupabaseToken("Token algorithm is not allowed")
            if algorithm == "HS256" and self.settings.supabase_jwt_secret is not None:
                signing_key: Any = self.settings.supabase_jwt_secret.get_secret_value()
            elif algorithm in self.settings.supabase_jwks_algorithms:
                kid = header.get("kid")
                if not isinstance(kid, str) or not kid:
                    raise InvalidSupabaseToken("Token key id is missing")
                jwk = await self._get_jwk(kid)
                if jwk.get("alg") not in (None, algorithm):
                    raise InvalidSupabaseToken("Token algorithm does not match its signing key")
                signing_key = PyJWK.from_dict(jwk, algorithm=algorithm).key
            else:
                raise InvalidSupabaseToken("Token algorithm is not allowed")

            claims = jwt.decode(
                token,
                signing_key,
                algorithms=list(allowed_algorithms),
                audience="authenticated",
                issuer=issuer,
                leeway=self.settings.supabase_jwt_leeway_seconds,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
            user_id = UUID(claims["sub"])
            email = claims.get("email")
            if email is not None and not isinstance(email, str):
                raise InvalidSupabaseToken("Token email claim is invalid")
            return VerifiedIdentity(user_id=user_id, email=email)
        except InvalidSupabaseToken:
            raise
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise InvalidSupabaseToken("Token claims or signature are invalid") from exc

    @property
    def _issuer(self) -> str | None:
        if not self.settings.supabase_url:
            return None
        return f"{self.settings.supabase_url.rstrip('/')}/auth/v1"

    async def _get_jwk(self, kid: str) -> dict[str, Any]:
        existing = self._keys.get(kid)
        if self.clock() >= self._expires_at or existing is None:
            await self._refresh_jwks(force=existing is None)
        key = self._keys.get(kid)
        if key is None:
            raise InvalidSupabaseToken("Signing key is not available")
        return key

    async def _refresh_jwks(self, force: bool = False) -> None:
        async with self._refresh_lock:
            if not force and self.clock() < self._expires_at:
                return
            if not self.settings.supabase_url:
                raise InvalidSupabaseToken("Supabase URL is not configured")
            url = f"{self.settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            try:
                response = await self.client.get(url)
                response.raise_for_status()
                payload = response.json()
                raw_keys = payload.get("keys") if isinstance(payload, dict) else None
                if not isinstance(raw_keys, list):
                    raise ValueError("JWKS response has no keys list")
                keys = {
                    item["kid"]: item
                    for item in raw_keys
                    if isinstance(item, dict)
                    and isinstance(item.get("kid"), str)
                    and item.get("kty") in {"RSA", "EC"}
                    and item.get("alg") in (None, *self.settings.supabase_jwks_algorithms)
                }
                if not keys:
                    raise ValueError("JWKS response contains no supported signing keys")
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                self._expires_at = self.clock() + min(self.cache_seconds, 30)
                if self._keys:
                    return
                raise InvalidSupabaseToken("Signing keys could not be loaded") from exc
            self._keys = keys
            self._expires_at = self.clock() + self.cache_seconds
