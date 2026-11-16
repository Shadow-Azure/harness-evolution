"""Runtime-keyed session-source adapter registry with fail-fast registration."""

from __future__ import annotations

from typing import ClassVar

from app.service.acquisition.parsers import (
    TraceParserFactory,
    UnsupportedTraceRuntime,
)
from app.third_party_api.session_source.base import BaseSessionSourceAdapter


class SessionSourceFactory:
    """Select one session-source adapter by envelope runtime without fallback."""

    _adapters: ClassVar[dict[str, type[BaseSessionSourceAdapter]]] = {}

    @classmethod
    def register(
        cls,
        adapter_cls: type[BaseSessionSourceAdapter],
    ) -> type[BaseSessionSourceAdapter]:
        """Register one subclass and reject a duplicate runtime identity."""
        key = adapter_cls.runtime_key
        if not key:
            raise RuntimeError("session source runtime_key must not be empty")
        if key in cls._adapters:
            raise RuntimeError(f"duplicate session source runtime: {key}")
        if key not in TraceParserFactory.registered_keys():
            raise RuntimeError(f"session source runtime has no trace parser: {key}")
        cls._adapters[key] = adapter_cls
        return adapter_cls

    @classmethod
    def create(cls, runtime_key: str) -> BaseSessionSourceAdapter:
        """Instantiate the adapter for one runtime or fail without fallback."""
        try:
            return cls._adapters[runtime_key]()
        except KeyError as exc:
            raise UnsupportedTraceRuntime(runtime_key) from exc

    @classmethod
    def registered_keys(cls) -> tuple[str, ...]:
        """Return registered runtime keys in stable order."""
        return tuple(sorted(cls._adapters))
