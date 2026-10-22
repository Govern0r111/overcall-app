from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from ..auth.ingest_keys import hash_key, looks_like_key
from .errors import err
from .ratelimit import Clock


@dataclass(frozen=True)
class KeyRecord:
    id: UUID
    user_id: UUID
    revoked: bool
    pepper_version: int = 1


class KeyStore(Protocol):
    async def find(self, key_hash: str) -> KeyRecord | None: ...

    async def rehash(
        self, key_id: UUID, old_hash: str, new_hash: str, pepper_version: int
    ) -> None: ...


class DbKeyStore:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    async def find(self, key_hash: str) -> KeyRecord | None:
        from sqlalchemy import select

        from ..db.models import IngestKey

        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(
                        IngestKey.id,
                        IngestKey.user_id,
                        IngestKey.revoked_at,
                        IngestKey.pepper_version,
                    ).where(IngestKey.key_hash == key_hash)
                )
            ).first()
        if row is None:
            return None
        return KeyRecord(
            id=row.id,
            user_id=row.user_id,
            revoked=row.revoked_at is not None,
            pepper_version=row.pepper_version,
        )

    async def rehash(self, key_id: UUID, old_hash: str, new_hash: str, pepper_version: int) -> None:
        from sqlalchemy import update

        from ..db.models import IngestKey

        async with self.session_factory() as session:
            await session.execute(
                update(IngestKey)
                .where(IngestKey.id == key_id, IngestKey.key_hash == old_hash)
                .values(key_hash=new_hash, pepper_version=pepper_version)
            )
            await session.commit()


class IngestAuthenticator:
    def __init__(
        self,
        store: KeyStore,
        pepper: str | None,
        pepper_prev: str | None = None,
        clock: Clock = time.monotonic,
        positive_ttl: float = 60.0,
        negative_ttl: float = 10.0,
        max_entries: int = 10_000,
        pepper_version: int = 1,
    ) -> None:
        self.store = store
        self.pepper = pepper
        self.pepper_prev = pepper_prev
        self.clock = clock
        self.positive_ttl = positive_ttl
        self.negative_ttl = negative_ttl
        self.max_entries = max_entries
        self.pepper_version = pepper_version
        self._cache: OrderedDict[str, tuple[float, KeyRecord | None]] = OrderedDict()

    async def authenticate(self, header_value: str | None) -> KeyRecord:
        if not self.pepper:
            raise err("not_ready")
        if not header_value or not header_value.strip():
            raise err("ingest_key_missing")
        key = header_value.strip()
        if not looks_like_key(key):
            raise err("ingest_key_invalid")
        digest = hash_key(key, self.pepper)
        now = self.clock()
        cached = self._cache.get(digest)
        if cached is not None and cached[0] > now:
            record = cached[1]
        else:
            record = await self.store.find(digest)
            if record is None and self.pepper_prev:
                previous_digest = hash_key(key, self.pepper_prev)
                record = await self.store.find(previous_digest)
                if record is not None and not record.revoked:
                    await self._rehash(record, previous_digest, digest)
            elif record is not None and not record.revoked:
                await self._rehash(record, digest, digest)
            ttl = self.positive_ttl if record is not None else self.negative_ttl
            self._cache.pop(digest, None)
            self._cache[digest] = (now + ttl, record)
            while len(self._cache) > self.max_entries:
                self._cache.popitem(last=False)
        if record is None:
            raise err("ingest_key_invalid")
        if record.revoked:
            raise err("ingest_key_revoked")
        return record

    async def _rehash(self, record: KeyRecord, old_hash: str, new_hash: str) -> None:
        if record.pepper_version == self.pepper_version:
            return
        rehash = getattr(self.store, "rehash", None)
        if rehash is not None:
            await rehash(record.id, old_hash, new_hash, self.pepper_version)

    def evict_key(self, key_id: UUID) -> None:
        stale = [
            digest
            for digest, (_, record) in self._cache.items()
            if record is not None and record.id == key_id
        ]
        for digest in stale:
            del self._cache[digest]
