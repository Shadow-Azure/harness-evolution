/** Display-only resolution for one attribution's object version evidence. */

export interface VersionLabelDisplay {
  ref: string | null;
  commit: string | null;
  digest: string | null;
  missing: boolean;
  full: string;
  copy: string | null;
}

const COMMIT_RE = /^[0-9a-f]{7,40}$/i;

function clean(value: string | null | undefined): string {
  return (value ?? "").trim();
}

/**
 * Resolve ref / commit / digest display values with the same priority as the
 * V2 prototype: explicit run evidence first, then a bare commit, then a plain
 * ref, and finally the content digest.
 * @param version Stored object version (usually a digest or legacy ref).
 * @param objectRef Human-readable ref from the displayed run.
 * @param objectCommit Commit from the displayed run.
 * @returns Display parts plus the full and copyable identifiers.
 */
export function resolveVersionLabel(
  version: string | null | undefined,
  objectRef: string | null | undefined,
  objectCommit: string | null | undefined,
): VersionLabelDisplay {
  const rawVersion = clean(version);
  let ref = clean(objectRef);
  let commit = clean(objectCommit);

  // Defensive fallbacks for callers that still pass a digest or a bare commit
  // through the ref slot.
  if (ref.startsWith("digest:") || ref.startsWith("provider:")) {
    ref = "";
  }
  if (ref && COMMIT_RE.test(ref)) {
    if (!commit) commit = ref;
    ref = "";
  }

  const rawIsDigest = /^digest:/.test(rawVersion);
  const rawIsCommit = COMMIT_RE.test(rawVersion);
  if (!ref && !commit && rawVersion && !rawIsDigest && !rawIsCommit) {
    ref = rawVersion;
  }
  if (!commit && rawIsCommit) {
    commit = rawVersion;
  }

  if (!ref && !commit && !rawVersion) {
    return {
      ref: null,
      commit: null,
      digest: null,
      missing: true,
      full: "版本未固定",
      copy: null,
    };
  }

  const digest = !ref && !commit ? rawVersion || null : null;
  const full = [ref, commit].filter(Boolean).join(" ") || digest || rawVersion || "版本未固定";
  const copy = commit || ref || digest || null;
  return {
    ref: ref || null,
    commit: commit || null,
    digest,
    missing: false,
    full,
    copy,
  };
}
