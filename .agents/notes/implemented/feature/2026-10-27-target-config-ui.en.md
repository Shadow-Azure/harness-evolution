# Agent Note: Target Configuration Authority and View Boundaries

Status: implemented

English | [中文](2026-10-27-target-config-ui.md)

## Problem

Evolution needs a place to manage skills and agents that may be changed, but that page combines remote git validation, admin-only writes, disabled configurations that must remain editable, and a wizard that may only select enabled rows. If the page decides whether a repository is reachable, hides disabled rows, or reports 422/409 only as transient notices, users lose input, cannot re-enable a configuration, and the frontend can disagree with the backend. The baseline field must also accept ordinary branch or tag text while offering tags from a saved target; making suggestion selection a prerequisite for assignment causes that text to disappear on blur or submit.

## Decision

`/evolution/targets` uses the prototype's exported light tokens, compact layout, cards, and status colors rather than introducing a second visual language; its new form follows the prototype's spacing, borders, and primary-action hierarchy. The configuration collection includes enabled and disabled rows, while the wizard catalog includes enabled rows only. The page hides write controls by role: members can read, while admins can create, edit, toggle, and delete. The baseline field is an editable combobox: input text enters the form immediately, while tags from a saved target are optional suggestions; an empty or failed suggestion request still permits direct input and save. Create mode has no target id, so it neither requests nor shows version loading. Edit mode shows loading only during a real request, and a changed draft repository URL marks suggestions as data from the saved configuration. The backend target service validates repository, ref, and subdirectory syntax and path rules, while `GitRemote` validates remote reachability and ref availability. `REPO_INVALID` stays in the open form without discarding input, and `TARGET_IN_USE` stays in the list context. Every successful write invalidates both `["evolution","targets"]` and `["catalogs"]`, so configuration and the future wizard share one refresh boundary. The gear entry in the `/evolution` page header makes this Issue discoverable; when M5-05 adds the wizard, the final entry is the inline "配置页" link inside the Step1 hint text, and the selector-side gear button is removed because its 13px gray text was too hidden.

## Alternatives considered

Probing repositories in the browser or duplicating URL/path/ref rules would create a second security authority and unnecessary remote traffic; filtering disabled rows out of the configuration collection would prevent users from re-enabling them; showing 422/409 only as a transient toast would discard complex form input and make an active-run conflict impossible to review; inventing a darker demo-oriented visual system for the new page would diverge from the prototype. All were rejected.

## Consequences

Remote feedback on the configuration page is bounded by backend timeouts, and the browser does not predict repository reachability; tag suggestions are likewise not a save prerequisite, so a failed request only reduces convenience. Members see configuration facts without attempting forbidden writes. The future wizard must keep consuming the enabled-only catalog rather than the configuration collection. Visual changes must start in the prototype and shared tokens so this page follows them instead of developing local styles.
