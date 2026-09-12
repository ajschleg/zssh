#!/usr/bin/env bash
# Symlink zssh into a directory on your PATH and install shell completions.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="${1:-$HOME/.local/bin}"

mkdir -p "$DEST_DIR"
ln -sf "$SRC_DIR/bin/zssh" "$DEST_DIR/zssh"
echo "linked $DEST_DIR/zssh -> $SRC_DIR/bin/zssh"

# zsh completion: drop it somewhere on $fpath.
ZSH_COMP_DIR="${ZSH_COMP_DIR:-$HOME/.zsh/completions}"
mkdir -p "$ZSH_COMP_DIR"
ln -sf "$SRC_DIR/completions/_zssh" "$ZSH_COMP_DIR/_zssh"
echo "linked $ZSH_COMP_DIR/_zssh"

case "${SHELL:-}" in
  */zsh)
    if ! grep -qs "$ZSH_COMP_DIR" "$HOME/.zshrc" 2>/dev/null; then
      cat <<MSG

To enable completions, add this to ~/.zshrc (above any existing compinit):
  fpath=($ZSH_COMP_DIR \$fpath)
  autoload -Uz compinit && compinit
MSG
    fi
    ;;
  */bash)
    echo
    echo "To enable completions, add this to ~/.bashrc:"
    echo "  source $SRC_DIR/completions/zssh.bash"
    ;;
esac

case ":$PATH:" in
  *":$DEST_DIR:"*) ;;
  *) echo
     echo "note: $DEST_DIR is not on your PATH. Add this to ~/.zshrc:"
     echo "  export PATH=\"$DEST_DIR:\$PATH\"" ;;
esac
