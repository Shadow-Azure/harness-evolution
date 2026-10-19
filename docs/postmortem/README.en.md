# Incident Reviews

English | [中文](README.md)

`docs/postmortem/` is the only narrative history layer: it records incidents that happened, their impact, root cause, response and recurrence prevention. Numbered files `yyyy-mm-dd-topic.md` are browsed by directory and stay out of the documentation map.

## Structure

Every review contains, in order:

1. **Impact**: who was affected, for how long, whether data was lost.
2. **Timeline**: discovery, mitigation, recovery and review moments.
3. **Root cause**: direct trigger and systemic conditions written separately.
4. **Response**: completed fixes and their verification.
5. **Prevention**: mechanically checkable gates or process changes, each linked to an issue.

## Rules

- Record only what happened; mark uncertainty explicitly.
- Never blame individuals; focus on system conditions and improvable interfaces.
- Prevention must land as code, a gate or a process item, never as "pay more attention".
- Keep rationale separate: system trade-offs go to Agent Notes, incident narrative stays here.
