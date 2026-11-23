# Agent Note: Evolution safe boundary pause

Status: implemented

English | [中文](2026-11-20-evolution-pause-resume.md)

## Problem

Evolution lacks user-controlled recoverable pause. Abnormal interruption leaves uncertain side effects and does not provide pause semantics.

## Decision

Persist durable control separate from execution stage: persist intent, save artifacts at safe boundaries and release the worker; resume the same run, commit and external evaluation ID. Submitted evaluation may continue, with results collected without progression. Initial run and job creation share one transaction; claiming and pausing lock the run first. A failure racing with pause keeps blocked evidence and disables automatic retry. Historical runs with unprovable frozen inputs fail explicitly. Recovery chooses stages from durable workspace publication and per-cluster turns, retaining completed evaluations and persisted decisions. Local candidate replay restores the selected branch and frozen push target to avoid duplicate side effects.

## Alternatives considered

turn-only pause waits too long. Killing tasks can leave partial state or uncertain publication. Reusing blocked conflicts with automatic retry. Waiting inside a handler holds the serial worker.

## Consequences

All schedulers, conditional writes, restart recovery, evaluation timeouts and workspace retention must agree. Pause cannot guarantee immediate external compute cancellation or allow editing frozen input.
