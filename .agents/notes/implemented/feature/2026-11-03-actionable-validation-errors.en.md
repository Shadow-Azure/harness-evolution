# Agent Note: Cross-interaction validation errors use a frontend explanation layer

Status: implemented

English | [中文](2026-11-03-actionable-validation-errors.md)

## Problem

The backend already provides stable `code` values and sanitized `details`, yet pages separately showed English `request validation failed`, raw domain phrases, or only “retry later”, leaving users unable to locate a field or choose the next action.

## Decision

The frontend adds shared `formatApiError` and `formatValidationDetails`; callers supply an operation-specific fallback. The helper maps 422 field paths and validation types first, then stable network, permission, service, and conflict codes. Unknown English phrases and exception content never become user copy.

## Alternatives considered

Returning Chinese directly from the backend would couple the protocol to one frontend language and UI wording. Changing copy independently in each page would duplicate mappings and preserve inconsistency.

## Consequences

Login, password change, sync handling, the evolution wizard, and run retry now share one error-explanation path. Unknown field paths still receive generic input guidance, and old responses without `details` retain scenario fallbacks. Target-specific git diagnostics and deep field hints remain owned by issue `#185`.
