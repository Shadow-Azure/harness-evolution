"""Registry and settings entry point for bad-case sync sources.

``HE_BAD_CASE_SYNC_PROVIDER`` is the only global-line switch: unset or blank
keeps the line off, an unknown value fails startup (never a silent fallback),
and a configured value builds exactly one source through its ``from_settings``.
The composition root reads the setting once; runtime code never reads it again.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from app.third_party_api.bad_case_sync_source.base import BaseBadCaseSyncSource

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)


class BadCaseSyncSourceFactory:
    """Select one bad-case sync source from deployment configuration."""

    _registry: ClassVar[dict[str, type[BaseBadCaseSyncSource]]] = {}

    @classmethod
    def register(
        cls,
        source_cls: type[BaseBadCaseSyncSource],
    ) -> type[BaseBadCaseSyncSource]:
        """Register one subclass and reject a duplicate provider identity."""
        key = source_cls.provider
        if not key:
            raise ValueError("bad-case sync source provider must not be empty")
        if key in cls._registry:
            raise ValueError(f"duplicate bad-case sync provider: {key}")
        cls._registry[key] = source_cls
        return source_cls

    @classmethod
    def registered_keys(cls) -> tuple[str, ...]:
        """Return registered provider keys in stable order."""
        return tuple(sorted(cls._registry))

    @classmethod
    def provider_key(cls, settings: Settings) -> str | None:
        """Return the normalized configured provider, or ``None`` when unset."""
        raw = settings.bad_case_sync_provider
        if raw is None:
            return None
        normalized = raw.strip().lower()
        return normalized or None

    @classmethod
    def create(cls, provider: str, settings: Settings) -> BaseBadCaseSyncSource:
        """Instantiate one named source; an unknown provider fails startup."""
        normalized = provider.strip().lower()
        implementation = cls._registry.get(normalized)
        if implementation is None:
            choices = ", ".join(cls.registered_keys())
            raise ValueError(
                f"unknown bad-case sync provider: {normalized!r}; expected one of: {choices}",
            )
        cls._require_endpoints(normalized, settings)
        return implementation.from_settings(settings)

    @classmethod
    def _require_endpoints(cls, provider: str, settings: Settings) -> None:
        """Fail startup when the switch is on but its endpoints cannot work.

        A provider without its base URL or Bearer token would otherwise start
        cleanly and fail on every sync tick, which reads as a runtime outage
        instead of the configuration error it is.
        """
        missing: list[str] = []
        if not settings.session_query_configured:
            missing.append("HE_SESSION_QUERY_BASE_URL/HE_SESSION_QUERY_TOKEN")
        if not settings.bad_case_query_configured:
            missing.append("HE_BAD_CASE_QUERY_BASE_URL/HE_BAD_CASE_QUERY_TOKEN")
        if missing:
            raise ValueError(
                f"HE_BAD_CASE_SYNC_PROVIDER={provider} requires: " + ", ".join(missing),
            )

    @classmethod
    def from_settings(cls, settings: Settings) -> BaseBadCaseSyncSource | None:
        """Build the configured source, or ``None`` when the global line is off.

        A deployment that still carries the retired endpoint credentials but no
        provider keeps the line off and gets one assembly-time warning, so the
        upgrade cannot silently enable or silently disable the global line.
        """
        provider = cls.provider_key(settings)
        if provider is None:
            if settings.session_query_configured or settings.bad_case_query_configured:
                logger.warning(
                    "bad-case sync provider is unset; the global line stays disabled "
                    "(HE_BAD_CASE_SYNC_PROVIDER)",
                    extra={
                        "event": "bad_case_sync.provider_unset",
                        "session_query_configured": settings.session_query_configured,
                        "bad_case_query_configured": settings.bad_case_query_configured,
                    },
                )
            return None
        return cls.create(provider, settings)


__all__ = ["BadCaseSyncSourceFactory"]
