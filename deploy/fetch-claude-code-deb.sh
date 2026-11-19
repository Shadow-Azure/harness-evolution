#!/usr/bin/env bash
# Fetch the official Claude Code apt package for the server architecture.
#
# Runs on the GitHub Actions runner, not on the production server: the runner
# resolves the stable channel, downloads the signed-repository package, and
# verifies the SHA256 from the repository's Packages index before upload.
#
# Usage: fetch-claude-code-deb.sh <amd64|arm64> [version] [--resolve-only]
#   CLAUDE_CODE_VERSION may be passed as the second argument; empty selects the
#   highest stable version in the index.
#   --resolve-only prints only version=<...> without downloading.
#
# Output (stdout, parseable):
#   version=<apt version>
#   deb=<local path>          (download mode only)
#   sha256=<hex digest>       (download mode only)
set -euo pipefail

readonly APT_BASE="${CLAUDE_CODE_APT_BASE:-https://downloads.claude.ai/claude-code/apt/stable}"
readonly ARCH="${1:-amd64}"
readonly WANT_VERSION="${2:-}"
readonly MODE="${3:-}"

if [ "$ARCH" != "amd64" ] && [ "$ARCH" != "arm64" ]; then
  echo "unsupported architecture: $ARCH (expected amd64 or arm64)" >&2
  exit 2
fi
if [ -n "$MODE" ] && [ "$MODE" != "--resolve-only" ]; then
  echo "unsupported mode: $MODE (expected --resolve-only)" >&2
  exit 2
fi

CACHE_DIR="${CLAUDE_CODE_CACHE_DIR:-$HOME/.cache/claude-code}"
mkdir -p "$CACHE_DIR"

PACKAGES="$(mktemp)"
trap 'rm -f "$PACKAGES"' EXIT
curl -fsSL --retry 3 --retry-delay 2 --max-time 120 \
  "$APT_BASE/dists/stable/main/binary-$ARCH/Packages" -o "$PACKAGES"

# Parse the index with Python: choose the requested version or the highest
# stable version, and emit version, filename, and SHA256 on one line.
RESOLVED="$(python3 - "$PACKAGES" "$WANT_VERSION" <<'PY'
import re
import sys

path, want = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
entries = []
for paragraph in text.split("\n\n"):
    fields = {}
    for line in paragraph.splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            fields[key] = value
    if fields.get("Package") == "claude-code":
        entries.append(fields)
if not entries:
    sys.exit("no claude-code package in the apt index")


def version_key(version):
    return tuple(int(part) if part.isdigit() else 0 for part in re.split(r"[.\-]", version))


if want:
    matches = [entry for entry in entries if entry.get("Version") == want]
    if not matches:
        sys.exit(f"claude-code version {want} is not in the stable index")
    entry = matches[0]
else:
    entry = max(entries, key=lambda item: version_key(item.get("Version", "")))

missing = [key for key in ("Version", "Filename", "SHA256") if not entry.get(key)]
if missing:
    sys.exit(f"apt index entry is missing {', '.join(missing)}")
print(entry["Version"], entry["Filename"], entry["SHA256"])
PY
)"

read -r VERSION FILENAME SHA256 <<<"$RESOLVED"

if [ "$MODE" = "--resolve-only" ]; then
  printf 'version=%s\n' "$VERSION"
  exit 0
fi

DEB="$CACHE_DIR/claude-code_${VERSION}_${ARCH}.deb"

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

if [ -f "$DEB" ] && [ "$(sha256_of "$DEB")" = "$SHA256" ]; then
  echo "using cached $DEB" >&2
else
  TMP="$DEB.part"
  rm -f "$TMP"
  echo "downloading $APT_BASE/$FILENAME" >&2
  curl -fsSL --retry 3 --retry-delay 2 --max-time 600 -o "$TMP" "$APT_BASE/$FILENAME"
  ACTUAL="$(sha256_of "$TMP")"
  if [ "$ACTUAL" != "$SHA256" ]; then
    rm -f "$TMP"
    echo "SHA256 mismatch for $FILENAME: expected $SHA256, got $ACTUAL" >&2
    exit 1
  fi
  mv "$TMP" "$DEB"
fi

printf 'version=%s\n' "$VERSION"
printf 'deb=%s\n' "$DEB"
printf 'sha256=%s\n' "$SHA256"
