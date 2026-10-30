# Agent Note: The target config page links back to /evolution

Status: implemented

English | [中文](2026-10-30-target-config-back-entry.md)

## Problem

After entering `/evolution/targets` from the launch wizard or the `/evolution` page head, the target config page offered no way back to the evolution page (#151); users had to detour through the top navigation. ClusterPreview and RunDetail already have return paths — only the config page lacked one.

## Decision

Add a `RouterLink to="/evolution"` link labelled「← 返回自进化」at the top of the config page content, styled like RunDetail's `.back` (12px dim text, hover/focus blue), with `data-testid="target-config-back"` as a stable test hook. An explicit `to="/evolution"` beats `router.back()`: predictable on direct entry, refresh, and new tabs, and isomorphic with the existing return paths. The unit test asserts the link exists with `href` `/evolution`; the E2E test clicks it in a real browser and asserts landing on `/evolution`.

## Alternatives considered

`router.back()` rejected: no history on direct entry, unpredictable behavior. Placing the link in the `page-head` right side rejected: the prototype (targets page in harness-evolution.html) puts the back link above the title, and RunDetail already does the same — consistency reduces cognitive load. A new button component rejected: a static link does not warrant an abstraction.

## Consequences

The link stays visible in every state (data, empty, read failure) because it sits on the page skeleton, outside data branches; keyboard reachable (native `<a>`). If future pages link into the config page from elsewhere (e.g. the Session page), the target remains `/evolution` — it does not vary by origin, keeping the single "back to the evolution page" semantics.
