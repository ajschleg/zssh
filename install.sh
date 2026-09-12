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
    ZSHRC="$HOME/.zshrc"
    if grep -qs "zssh completions" "$ZSHRC" 2>/dev/null; then
      echo "completions already enabled in $ZSHRC"
    elif [ "${ZSSH_NO_RC_EDIT:-}" = "1" ]; then
      echo
      echo "To enable completions, add this to $ZSHRC above any compinit line:"
      echo "  fpath=($ZSH_COMP_DIR \$fpath)"
    else
      cp "$ZSHRC" "$ZSHRC.zssh-backup" 2>/dev/null || true
      # fpath must be set before compinit runs, so insert above the first
      # compinit line if there is one; otherwise append with our own compinit.
      if grep -qs "compinit" "$ZSHRC" 2>/dev/null; then
        awk -v dir="$ZSH_COMP_DIR" '
          !done && /compinit/ {
            print "# zssh completions"
            print "fpath=(" dir " $fpath)"
            done = 1
          }
          { print }
        ' "$ZSHRC" > "$ZSHRC.zssh-tmp" && mv "$ZSHRC.zssh-tmp" "$ZSHRC"
      else
        {
          echo ""
          echo "# zssh completions"
          echo "fpath=($ZSH_COMP_DIR \$fpath)"
          echo "autoload -Uz compinit && compinit"
        } >> "$ZSHRC"
      fi
      echo "enabled completions in $ZSHRC (backup: $ZSHRC.zssh-backup)"
      echo "run 'exec zsh' to pick them up in this shell"
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
