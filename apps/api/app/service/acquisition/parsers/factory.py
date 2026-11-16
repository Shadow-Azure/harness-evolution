"""Runtime-keyed trace parser registry with fail-fast registration."""

from __future__ import annotations

from typing import ClassVar

from app.service.acquisition.parsers.base import BaseTraceParser


class UnsupportedTraceRuntime(RuntimeError):
    """Raised when no registered parser owns a payload runtime identity."""

    def __init__(self, runtime_key: str) -> None:
        """Keep the unsupported key available without exposing payload content."""
        self.runtime_key = runtime_key
        super().__init__(f"unsupported trace runtime: {runtime_key}")


class TraceParserFactory:
    """Select one parser class by runtime and expose its current version."""

    _parsers: ClassVar[dict[str, type[BaseTraceParser]]] = {}

    @classmethod
    def register(
        cls,
        parser_cls: type[BaseTraceParser],
    ) -> type[BaseTraceParser]:
        """Register one subclass and reject a duplicate runtime identity."""
        key = parser_cls.runtime_key
        if not key:
            raise RuntimeError("trace parser runtime_key must not be empty")
        if key in cls._parsers:
            raise RuntimeError(f"duplicate trace runtime: {key}")
        cls._parsers[key] = parser_cls
        return parser_cls

    @classmethod
    def create(cls, runtime_key: str) -> BaseTraceParser:
        """Instantiate the parser for one runtime or fail without fallback."""
        try:
            return cls._parsers[runtime_key]()
        except KeyError as exc:
            raise UnsupportedTraceRuntime(runtime_key) from exc

    @classmethod
    def versions(cls) -> dict[str, int]:
        """Return the current parser version for every registered runtime."""
        return {key: parser.parser_version for key, parser in cls._parsers.items()}

    @classmethod
    def registered_keys(cls) -> tuple[str, ...]:
        """Return registered runtime keys in stable order."""
        return tuple(sorted(cls._parsers))
