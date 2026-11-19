#!/usr/bin/env bash
# Fetch a pinned Xray-core release for the server architecture.
#
# Runs on the GitHub Actions runner, not on the production server: the runner
# downloads the official release over HTTPS and verifies the pinned SHA256
# before upload, so a server that cannot reach GitHub never has to bootstrap
# its own proxy client. The extracted directory contains xray, geoip.dat, and
# geosite.dat, which the sample routing rules in docs/git-proxy.md reference.
#
# Usage: fetch-xray.sh <amd64|arm64>
#
# Output (stdout, parseable):
#   version=<tag>
#   dir=<local directory>
#   sha256=<hex digest>
set -euo pipefail

readonly VERSION="v26.11.9"
readonly ARCH="${1:-amd64}"

case "$ARCH" in
  amd64)
    readonly ASSET="Xray-linux-64.zip"
    readonly SHA256="b651f7e1d9966ee2c1b1ee1bf8b52c72771824d3065dce96bbc8bcc19ed95f82"
    ;;
  arm64)
    readonly ASSET="Xray-linux-arm64-v8a.zip"
    readonly SHA256="64ed6858982a7f5eb85d88b811089063bd4f17561f4c8f44e0f1dc8e6f6430be"
    ;;
  *)
    echo "unsupported architecture: $ARCH (expected amd64 or arm64)" >&2
    exit 2
    ;;
esac

CACHE_DIR="${XRAY_CACHE_DIR:-$HOME/.cache/xray}"
mkdir -p "$CACHE_DIR"
OUT="$CACHE_DIR/${VERSION}-${ARCH}"
ZIP="$CACHE_DIR/${VERSION}-${ARCH}.zip"

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

if [ ! -f "$ZIP" ] || [ "$(sha256_of "$ZIP")" != "$SHA256" ]; then
  TMP="$ZIP.part"
  rm -f "$TMP"
  echo "downloading $ASSET ($VERSION)" >&2
  curl -fsSL --retry 3 --retry-delay 2 --max-time 600 \
    "https://github.com/XTLS/Xray-core/releases/download/$VERSION/$ASSET" -o "$TMP"
  ACTUAL="$(sha256_of "$TMP")"
  if [ "$ACTUAL" != "$SHA256" ]; then
    rm -f "$TMP"
    echo "SHA256 mismatch for $ASSET: expected $SHA256, got $ACTUAL" >&2
    exit 1
  fi
  mv "$TMP" "$ZIP"
fi

rm -rf "$OUT"
mkdir -p "$OUT"
unzip -q -o "$ZIP" -d "$OUT"
if [ ! -x "$OUT/xray" ]; then
  echo "release archive does not contain an xray binary" >&2
  exit 1
fi
chmod 0755 "$OUT/xray"
# Geo data ships in the same archive; routing rules such as geosite:google need it.
for file in geoip.dat geosite.dat; do
  if [ -f "$OUT/$file" ]; then
    chmod 0644 "$OUT/$file"
  fi
done

if ! "$OUT/xray" version 2>/dev/null | head -1 | grep -Fq "${VERSION#v}"; then
  echo "downloaded xray does not report $VERSION" >&2
  exit 1
fi

printf 'version=%s\n' "$VERSION"
printf 'dir=%s\n' "$OUT"
printf 'sha256=%s\n' "$SHA256"
