"""Trace-shape parser registry with fail-fast registration and explicit dispatch."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from app.service.acquisition.parsers.base import BaseTraceParser, TracePayload


class UnsupportedTraceRuntime(RuntimeError):
    """Raised when no registered parser owns a payload runtime identity."""

    def __init__(self, runtime_key: str) -> None:
        """Keep the unsupported key available without exposing payload content."""
        self.runtime_key = runtime_key
        super().__init__(f"unsupported trace runtime: {runtime_key}")


class AmbiguousTraceRuntime(RuntimeError):
    """Raised when more than one registered parser accepts the same trace shape."""

    def __init__(self, runtime_keys: Sequence[str]) -> None:
        """Keep the ambiguous runtime identities without exposing payload content."""
        self.runtime_keys = tuple(sorted(runtime_keys))
        joined = ", ".join(self.runtime_keys)
        super().__init__(f"ambiguous trace runtime: {joined}")


class TraceParserFactory:
    """Select one session parser by trace shape and expose per-runtime versions."""

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
    def for_trace(cls, payloads: Sequence[TracePayload]) -> BaseTraceParser:
        """Instantiate the unique parser whose ``can_parse`` accepts the trace."""
        matches = [
            parser_cls for parser_cls in cls._parsers.values() if parser_cls.can_parse(payloads)
        ]
        if not matches:
            raise UnsupportedTraceRuntime(
                payloads[0].runtime_key if payloads else "unknown",
            )
        if len(matches) > 1:
            raise AmbiguousTraceRuntime([parser_cls.runtime_key for parser_cls in matches])
        return matches[0](payloads)

    @classmethod
    def create(
        cls,
        runtime_key: str,
        payloads: Sequence[TracePayload],
    ) -> BaseTraceParser:
        """Instantiate an explicitly named parser without trace-shape selection."""
        try:
            parser_cls = cls._parsers[runtime_key]
        except KeyError as exc:
            raise UnsupportedTraceRuntime(runtime_key) from exc
        return parser_cls(payloads)

    @classmethod
    def for_payload(
        cls,
        runtime_key: str,
        payload: TracePayload,
    ) -> BaseTraceParser:
        """Instantiate a parser for the single-payload compatibility facade."""
        try:
            parser_cls = cls._parsers[runtime_key]
        except KeyError as exc:
            raise UnsupportedTraceRuntime(runtime_key) from exc
        return parser_cls.for_single_payload(payload)

    @classmethod
    def version(cls, runtime_key: str) -> int:
        """Read one runtime's current parser version without instantiating it."""
        try:
            return cls._parsers[runtime_key].parser_version
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
