"""Provider registry and startup selection for bad-case sync sources."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, ClassVar

from app.third_party_api.bad_case_sync_source.base import BaseBadCaseSyncSource

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

PROVIDER_ENV = "HE_BAD_CASE_SYNC_PROVIDER"


class BadCaseSyncSourceFactory:
    """Select one bad-case sync source from deployment configuration."""

    _registry: ClassVar[dict[str, type[BaseBadCaseSyncSource]]] = {}

    @classmethod
    def register(
        cls,
        source_cls: type[BaseBadCaseSyncSource],
    ) -> type[BaseBadCaseSyncSource]:
        """Register one subclass and reject an empty or duplicate provider."""
        provider = source_cls.provider.strip().lower()
        if not provider:
            raise RuntimeError("bad-case sync source provider must not be empty")
        if provider in cls._registry:
            raise RuntimeError(f"duplicate bad-case sync source provider: {provider}")
        cls._registry[provider] = source_cls
        return source_cls

    @classmethod
    def provider_key(cls, settings: Settings) -> str | None:
        """Return the normalized configured provider, or None when unset."""
        configured = settings.bad_case_sync_provider
        if configured is None:
            return None
        normalized = configured.strip().lower()
        return normalized or None

    @classmethod
    def from_settings(cls, settings: Settings) -> BaseBadCaseSyncSource | None:
        """Build the configured provider once at composition time.

        A missing provider keeps the global line disabled. Legacy endpoint
        credentials alone never enable it; a warning points the operator at the
        missing switch instead of silently inferring intent.
        """
        provider = cls.provider_key(settings)
        if provider is None:
            if settings.session_query_configured or settings.bad_case_query_configured:
                logger.warning(
                    "bad-case sync endpoints are configured but %s is unset; "
                    "the global sync line stays disabled",
                    PROVIDER_ENV,
                )
            return None
        return cls.create(provider, settings)

    @classmethod
    def create(cls, provider: str, settings: Settings) -> BaseBadCaseSyncSource:
        """Instantiate one provider; an unknown value fails startup."""
        normalized = provider.strip().lower()
        implementation = cls._registry.get(normalized)
        if implementation is None:
            known = ", ".join(sorted(cls._registry)) or "none"
            raise ValueError(f"{PROVIDER_ENV} must be one of: {known}")
        return implementation.from_settings(settings)

    @classmethod
    def registered(cls) -> Mapping[str, type[BaseBadCaseSyncSource]]:
        """Return a read-only view of the registry for diagnostics."""
        return dict(cls._registry)


__all__ = ["PROVIDER_ENV", "BadCaseSyncSourceFactory"]
