# Agent Note: Launch wizard shows preview progress and timeout feedback

Status: implemented

English | [中文](2026-11-19-launch-wizard-loading-feedback.md)

## Problem

Clicking “Next: associate Sessions” on step 1 of “Launch self-evolution” synchronously calls `preview/sessions`. Before matching Sessions, the server resolves the selected version into a body hash. On an empty local mirror cache, `SubprocessGitContent` runs `git clone --mirror` against the target repository and the whole read is capped at 20 seconds. A cold cache or slow GitHub access therefore makes this step wait until it times out. On 2026-11-19 at 18:38, deploy #388 moved `HE_DATA_DIR` to a brand-new `/var/lib/harness-evolution/data` (the deploy log shows the directory did not exist before), and the old `target-content` cache was not migrated. #385 had fixed the unwritable cache directory, so this was the first request that actually reached the clone. When the user clicked Next at 19:26 they saw only a disabled button and roughly 20 seconds of silence, then a “target file read timed out” message under the version field.

`LaunchWizard.vue` only disables the button while `pending`. It neither says whether the server is resolving the version or associating Sessions, nor shows elapsed time; the user cannot distinguish “cloning” from “the page froze”. The timeout is also reported only as red text under the version field, without a cause, retry, or the explanation that this is not an empty Session result. A backend speed-up cannot remove the problem entirely because the first remote-repository read is inherently slow; the entry point must make the wait legible.

## Decision

- The V2 prototype shows a read-only progress card between the step strip and the form while a preview is pending:
  - Step 1 lists “read target version → associate Sessions”, step 2 lists “filter potential bad cases”, and step 3 lists “check attribution cache”. Completed stages are checked, the current stage is highlighted, and later stages stay muted.
  - It shows elapsed seconds and states “usually 2–5 seconds; the first read must clone the repository, the server read cap is about 20 seconds, and a timeout offers retry”, plus “an empty cache first clones the remote repository”. It never uses a fake progress bar or countdown and never promises that a wait beyond the cap will succeed.
  - The primary button immediately switches to the current stage label (for example “Reading target version…”) with a spinner. The form stays visible but becomes muted and non-interactive so conditions cannot change mid-wait.
  - While waiting, “Cancel wait” returns to the same step and keeps the entered conditions; the production request may continue and its result is discarded.
- The timeout state reuses the same card: it says the server reached its read cap without finishing the target file, that this is not an empty Session result, and offers “Retry resolution” and “Back to edit conditions”. The version field also turns red, matching the field-level feedback of production `TARGET_CONTENT_UNRESOLVED`. Other content reasons keep the inline field error.
- Accessibility: the waiting card uses `role=status`, the timeout card uses `role=alert`; the per-second elapsed text is `aria-hidden` and is not put in a live region; the disabled primary button still carries the current stage label. Production adds `prefers-reduced-motion` handling that the prototype does not have.
- The prototype pins the waiting and timeout states with `wzsim=loading` and `wzsim=timeout` query parameters so the same scenario can be captured; a normal click advances to the next step after four seconds.
- Production `LaunchWizard.vue` implements the same interaction: a `previewBusy` state with a one-second ticker and a request generation counter; step-forward previews show the progress card while the form is `inert`/locked; a `content_timeout`/`timeout` failure shows the failed card with retry/back; cancel advances the generation and discards late results without changing `http.ts` or adding AbortController. The server reports no substage progress, so step 1 keeps “read target version” current and “associate Sessions” waiting instead of faking completion.

## Alternatives considered

- **One centered spinner for the whole modal**: rejected. It erases the selected scope and entered conditions, so the user cannot confirm what they are waiting for; the progress card preserves context.
- **Only a button spinner, no stages**: rejected. The user still cannot tell whether the delay is version resolution or Session association, or that the first clone may be slower; the stage list answers “what is this step doing”.
- **A fake progress bar or countdown**: rejected. The server has no percentage to report; a fake progress bar would be exposed on timeout and would make later honest progress less trustworthy.
- **Only lengthening the timeout red text**: rejected. The timeout happens after 20 seconds, while the first 20 seconds still have no feedback; cause, retry, and “not an empty Session result” belong with the wait.
- **Automatic retry**: rejected. Retrying a cold clone repeats the wait and hides the fact that the target repository is unreachable or too slow, which the user or operator must handle; keep an explicit retry.
- **Move the clone to a background job and poll from the frontend**: this is the more thorough backend option, but it changes the synchronous `preview/*` contract, job state, and cache semantics, so it is out of scope for this prototype; it is recorded as a follow-up option in the issue.

## Consequences

- The prototype clearly shows where a slow preview spends its time, how long it has waited, and what to do after a failure; the user can cancel without losing the form.
- Production is implemented and passed a real-browser smoke: waiting card, stage-aware button, locked form, cancel, injected 20-second timeout state, and retry/back all work. The smoke uses a local SQLite fixture and CDP-injected 422 after 20 seconds to simulate `content_timeout`; it is not real GitHub latency or a real backend timeout. The wait remains cancellable and the form keeps its values. This change does not alter the 20-second timeout, the `preview/*` contract, or remove any real network read.
- There is no separate frontend watchdog: if the request hangs on a proxy/network and never settles, the waiting card stays until the user cancels; a 504/non-JSON response becomes the generic `requestError`, not the timeout card. Only a server `content_timeout`/`timeout` becomes the card.
- Because the server reports no substage progress, production step 1 keeps “associate Sessions” waiting for the whole request instead of advancing to it like the prototype demo; this is an intentional honest degradation, not a missing implementation.
- Cancel only discards the frontend result; it does not abort the request that already left the browser. The request generation prevents a late response from advancing the step. In-step pagination and the step-4 cache refresh keep the previous disabled-state treatment without this card.
- The timeout card covers `content_timeout`/`timeout` only; `ref_not_found`, `repo_unreachable`, and other content errors keep the inline field error so not every content failure is described as a timeout. The first clone is a common cause, not the only possible one.
- The backend can still improve separately: read a single file directly, fetch only the target ref shallowly, warm the mirror in the background, or make the request asynchronous. These complement the frontend feedback rather than replace it.
- The prototype's demo states are pinned by query parameters and are not evidence of real latency or a real timeout; production evidence comes from the real-browser smoke (local fixture + CDP-injected 422) and real application screenshots, while real backend/GitHub latency still needs observation after deploy.
