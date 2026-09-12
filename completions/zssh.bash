# bash completion for zssh.
_zssh_complete() {
  local cur prev cmd
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"
  cmd="${COMP_WORDS[1]}"

  local commands="add remove rm list ls connect terminal term exec close status config-path"

  if [ "$COMP_CWORD" -eq 1 ]; then
    COMPREPLY=( $(compgen -W "$commands --help --version" -- "$cur") )
    return
  fi

  case "$prev" in
    -i|--identity) COMPREPLY=( $(compgen -f -- "$cur") ); return ;;
    -t|--target)   COMPREPLY=( $(compgen -W "$(zssh __targets --live 2>/dev/null)" -- "$cur") ); return ;;
    --ttl)         COMPREPLY=( $(compgen -W "300 900 1800 3600 7200" -- "$cur") ); return ;;
  esac

  case "$cmd" in
    connect|remove|rm|status)
      if [ "$COMP_CWORD" -eq 2 ]; then
        COMPREPLY=( $(compgen -W "$(zssh __targets 2>/dev/null)" -- "$cur") )
      else
        COMPREPLY=( $(compgen -W "--ttl --detach --restart --json" -- "$cur") )
      fi
      ;;
    terminal|term|close)
      if [ "$COMP_CWORD" -eq 2 ]; then
        COMPREPLY=( $(compgen -W "$(zssh __targets --live 2>/dev/null) --all" -- "$cur") )
      fi
      ;;
    exec)
      COMPREPLY=( $(compgen -W "-t --target --tty" -- "$cur") )
      ;;
    add)
      if [ "$COMP_CWORD" -le 3 ] && [[ "$cur" != -* ]]; then
        COMPREPLY=( $(compgen -W "$(zssh __destinations 2>/dev/null)" -- "$cur") )
      else
        COMPREPLY=( $(compgen -W "-u -p -i -o -d --force" -- "$cur") )
      fi
      ;;
    list|ls)
      COMPREPLY=( $(compgen -W "--json" -- "$cur") )
      ;;
  esac
}
complete -F _zssh_complete zssh
