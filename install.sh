#!/usr/bin/env sh
set -eu

REPO="${VISUAL_EVIDENCE_GATEWAY_REPO:-scy7796/visual-evidence-gateway}"
VERSION="${VISUAL_EVIDENCE_GATEWAY_VERSION:-latest}"
BIN_DIR="${VISUAL_EVIDENCE_GATEWAY_BIN_DIR:-$HOME/.local/bin}"
INSTALL_PATH="$BIN_DIR/visual-evidence-gateway"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit "${2:-1}"
}

command -v curl >/dev/null 2>&1 || fail "curl is required to download the release binary." 2
if ! command -v codex >/dev/null 2>&1; then
  cat >&2 <<'EOF'
ERROR: Codex CLI is required but was not found.
Install the official CLI first, sign in with ChatGPT, then rerun this command:
  npm install -g @openai/codex
  codex
EOF
  exit 2
fi

case "$(uname -s)" in
  Linux) os="linux" ;;
  Darwin) os="macos" ;;
  *) fail "Unsupported operating system: $(uname -s)" 2 ;;
esac

case "$(uname -m)" in
  x86_64|amd64) arch="x86_64" ;;
  arm64|aarch64) arch="arm64" ;;
  *) fail "Unsupported CPU architecture: $(uname -m)" 2 ;;
esac

asset="visual-evidence-gateway-${os}-${arch}"
if [ -n "${VISUAL_EVIDENCE_GATEWAY_RELEASE_BASE:-}" ]; then
  base="${VISUAL_EVIDENCE_GATEWAY_RELEASE_BASE%/}"
elif [ "$VERSION" = "latest" ]; then
  base="https://github.com/${REPO}/releases/latest/download"
else
  case "$VERSION" in v*) tag="$VERSION" ;; *) tag="v$VERSION" ;; esac
  base="https://github.com/${REPO}/releases/download/${tag}"
fi

tmp="$(mktemp -d 2>/dev/null || mktemp -d -t visual-evidence-gateway)"
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

printf 'Downloading %s...\n' "$asset"
curl -fL --retry 3 --connect-timeout 15 -o "$tmp/$asset" "$base/$asset" \
  || fail "No compatible release binary was found at $base/$asset" 3

# A checksum protects against transfer corruption. Missing or malformed
# checksum metadata is a hard failure, never a silent skip.
if ! curl -fL --retry 2 --connect-timeout 15 -o "$tmp/SHA256SUMS.txt" \
  "$base/visual-evidence-gateway-SHA256SUMS.txt" >/dev/null 2>&1; then
  fail "SHA-256 checksum file could not be downloaded; refusing to install an unverified binary" 4
fi
expected="$(awk -v name="$asset" '$2 == name || $2 == "*" name {print $1; exit}' "$tmp/SHA256SUMS.txt")"
[ -n "$expected" ] || fail "SHA-256 checksum file does not contain an entry for $asset" 4
case "$expected" in
  *[!0-9a-f]*) fail "SHA-256 checksum entry is malformed" 4 ;;
esac
[ "${#expected}" -eq 64 ] || fail "SHA-256 checksum entry is malformed" 4
if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$tmp/$asset" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  actual="$(shasum -a 256 "$tmp/$asset" | awk '{print $1}')"
else
  fail "sha256sum or shasum is required to verify the release binary" 4
fi
[ "$actual" = "$expected" ] || fail "SHA-256 verification failed." 4

mkdir -p "$BIN_DIR"
chmod 0755 "$tmp/$asset"
mv -f "$tmp/$asset" "$INSTALL_PATH"
chmod 0755 "$INSTALL_PATH"

printf 'Installed: %s\n' "$INSTALL_PATH"
if ! "$INSTALL_PATH" setup "$@"; then
  rm -f "$INSTALL_PATH"
  rmdir "$BIN_DIR" 2>/dev/null || true
  fail "setup failed; the downloaded binary was rolled back" 5
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) : ;;
  *) printf '\nTip: add %s to PATH to run `visual-evidence-gateway` directly.\n' "$BIN_DIR" ;;
esac
