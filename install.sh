#!/usr/bin/env bash
# Symlink zssh into a directory on your PATH.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/bin/zssh"
DEST_DIR="${1:-$HOME/.local/bin}"

mkdir -p "$DEST_DIR"
ln -sf "$SRC" "$DEST_DIR/zssh"
echo "linked $DEST_DIR/zssh -> $SRC"

case ":$PATH:" in
  *":$DEST_DIR:"*) ;;
  *) echo "note: $DEST_DIR is not on your PATH. Add this to ~/.zshrc:"
     echo "  export PATH=\"$DEST_DIR:\$PATH\"" ;;
esac
