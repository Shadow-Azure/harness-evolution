# Agent Note: Permissions for the shared Claude Code version directory

Status: implemented

English | [中文](2026-11-23-claude-code-shared-directory-permissions.md)

## Problem

A production run's `cluster.review` failed during spawn (`AgentProviderError: claude-code analysis call could not start`, 10 ms, 0 tokens), while Deploy stayed green. The direct cause was the installer: it unpacked the deb into a `tempfile.mkdtemp()` directory (0700 by default) and renamed it with `os.replace()` to `/opt/harness/shared/claude-code/<version>`. The version directory kept 0700 and the `deploy` owner, but the service runs as `harness` and cannot traverse it to execute `current/usr/bin/claude`.

The existing preflight checked `prefix`, `config`, the settings file, and the binary's other-execute bit, but missed `<version>`, `usr`, and `usr/bin`. Deploy's `test -x` ran as deploy, which owns the directory, so it always passed. More importantly, a repeat deployment takes the configure-only path with `need_install=false` and never calls `install_from_deb()`, so fixing the preflight alone would not repair an existing 0700 directory.

## Decision

After extraction and before the rename, the installer sets staging and its `usr` / `usr/bin` directories to 0755 explicitly. The `binary.exists()` early-return branch and the configure-only path both call the same repair function, so rerunning Deploy repairs a historical directory. `preflight_shared_access()` walks from `prefix` to the binary checking other-execute on every level and keeps the settings other-read check; failure happens before `switch_current`.

The Deploy workflow no longer relies on `test -x`; it rechecks each level's other bits with `stat`. The `sudo -u harness` smoke test runs only when deploy already has that privilege, otherwise it warns explicitly and falls back to the bit checks. Bootstrap grants deploy only systemctl permissions, and this fix does not widen that sudo surface.

## Alternatives considered

- **Change only the preflight**: blocks the next bad deployment but cannot repair the existing 0700 directory, and the configure-only path never calls the install function.
- **ACL / root / `LoadCredential`**: needs root or a one-time `setfacl` initialization and violates the "prefer a pure pipeline" requirement.
- **0777**: lets harness traverse the directory but widens write access and violates least privilege.
- **Run the service as deploy**: a compromised service would inherit deploy's home, SSH deployment key, and release write access, which is unacceptable.
- **Grant deploy `sudo -u harness`**: needs root to change sudoers and widens the deployment account's lateral permissions; the bit checks already cover the portable subset.

## Consequences

- Rerunning Deploy repairs an existing 0700 version directory without a manual chmod.
- New extractions no longer produce a 0700 version directory; a preflight failure happens before `current` switches, and the old release keeps serving.
- Deploy cannot impersonate harness, so the pipeline can prove only the other bits; the harness-viewpoint `sudo -u harness ... --version` remains a separate acceptance step, with a real run's `cluster.review` as the final authority.
- The version directory, `usr`, and `usr/bin` are normalized to 0755. The installer assumes the deb contains that `usr` structure and fails explicitly when it is missing instead of silently skipping.
