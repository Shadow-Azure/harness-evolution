# Agent Note: Workspace attribution Skill interaction prototype

Status: implemented

English | [中文](2026-11-19-attribution-skill-prototype.md)

## Problem

Workspace attribution Skill packages have distinct upload and activation actions. Design text alone makes it difficult to check whether the list and effective prompt stay in sync and whether administrators and read-only users see the appropriate actions.

## Decision

Show package management within the existing V2 prototype's workspace administration page. The example ZIP, package list, and prompt share the same fixtures. The prototype keeps changes in memory per workspace. A read-only deep link lets reviewers verify download access and the visibility of write controls.

The library uses Workspace Admin’s compact tables and buttons. Resource details use the inset code preview from Ingest. Admins and read-only members can inspect the selected package in the same tab as the list.

## Alternatives considered

A static page would leave activation, deletion, and fallback transitions untested. Connecting the live package API and validating arbitrary ZIP archives would bring server-side dependencies into an interaction prototype.

A separate list frame duplicates the Workspace Admin content boundary and separates the table typography and control density from sibling tabs.

## Consequences

The page can independently demonstrate uploading, activating, falling back after deletion, and read-only access. Reviewers can download the example ZIP locally and select it again. Reloading restores the fixtures.
