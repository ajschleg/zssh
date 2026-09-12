# zssh

Named, persistent SSH sessions for humans *and* AI agents.

You keep a small address book of targets. `zssh connect prod` opens one real SSH
connection and drops you into a shell **in the tab you ran it from**. That
connection stays open in the background after you exit the shell, so an agent
can keep working on the same box with `zssh exec ...` — no re-auth, no new
handshake, same session state. It goes away when you run `zssh close`, or
automatically after an hour.

Built on OpenSSH's own connection multiplexing (`ControlMaster`), so there is no
daemon of its own to babysit and no credentials are stored anywhere.

## Install

```sh
git clone <this repo> && cd zssh
./install.sh              # symlinks bin/zssh into ~/.local/bin
./install.sh /usr/local/bin   # ...or wherever you like
```

Requires Python 3.8+ and OpenSSH 5.6+ — both already present on macOS, Linux
and the BSDs. Windows needs WSL; see [Platform support](#platform-support).

## Targets

```sh
zssh add me@mini.tail1d8ec6.ts.net       # named after the host: "mini"
zssh add prod deploy@10.0.0.7            # or name it yourself
zssh add gpu ubuntu@192.168.1.50:2222 -i ~/.ssh/lab_ed25519
zssh add jump root@203.0.113.9 -o ProxyJump=bastion -d "via bastion"
zssh list
zssh rm gpu
```

`add` takes `[user@]host[:port]` — an IP, a DNS name, a Tailscale MagicDNS name,
or anything else your ssh resolves. Give one argument and the target is named
after the host's first label (`db1.internal.example.com` becomes `db1`); a bare
IP has no such label, so name it yourself. `-u/-p/-i` override the pieces, `-o` passes any
`ssh -o` option through (repeatable), `-d` adds a note. The address book is a
plain JSON file — `zssh config-path` prints where.

## Connect

```sh
zssh connect prod            # opens the session, then a shell right here
zssh connect prod --detach   # open the session only (what a script/agent wants)
zssh connect prod --ttl 7200 # keep it alive up to 2 hours instead of 1
```

The shell replaces the `zssh` process itself (`exec`), so you land on the remote
host in the same terminal tab — no nested window, no new pane. Exiting the shell
drops you back to your local prompt but **leaves the session open**.

### The remote prompt

Inside a `zssh` shell the prompt is the target's name, so you always know which
box you're typing into:

```
zssh@prod:~%            # instead of deploy@f8638616-8d8f-4794-9257-8f36914a6f9a
```

It works by writing a throwaway startup file on the target (in a `0700` `mktemp`
directory), sourcing your own rc files first and then appending a prompt hook —
so your environment, aliases and PATH are exactly what they'd normally be. The
shim deletes itself once the shell has read it, and nothing on the target is
modified permanently.

Supported for remote `zsh` and `bash`. Any other login shell (fish, sh, csh),
or any hiccup writing the file, silently falls back to the shell's own prompt —
`connect` never fails over cosmetics. Opt out per command with `--no-prompt`, or
for good with `ZSSH_PROMPT=0`.

## Use the open session

```sh
zssh terminal            # shell on the open session again, same tab
zssh terminal prod       # ...a specific one
zssh exec uptime         # run a command over the existing connection
zssh exec -t prod uptime # ...on a named target
zssh exec 'cd /srv/app && git pull'
zssh status              # what's open and how long it has left
zssh close               # hang up
zssh close --all
```

`exec` streams stdout/stderr straight through and exits with the remote command's
exit code, so it composes normally with shell scripts and CI.

Quoting: multiple arguments are passed through literally
(`zssh exec echo "a b"` prints `a b`). For remote shell syntax — pipes,
redirection, `$VARS`, `&&` — pass one quoted string:
`zssh exec 'grep -c ERROR /var/log/app.log || echo none'`.

When only one session is open, `terminal`/`exec`/`close` don't need a target
name. With several open, name one with `-t` (or `zssh close prod`); `connect`
remembers the most recent as the default.

## Using it with an AI agent

This is the point of the tool. Authenticate once, yourself, then let the agent
work over that already-open connection:

```sh
zssh connect prod --detach      # you do this, once, with your key/2FA/password
```

Then the agent only ever needs:

```sh
zssh exec <command>             # runs on prod, reuses your session
zssh status --json              # is it still open? how long left?
```

The agent never handles a credential, and the blast radius is bounded by the
TTL — after an hour the session closes itself even if nobody remembers to.

Be clear-eyed about what this does *not* do: it is not a sandbox. `zssh exec`
runs arbitrary commands as your user on that host, and if your key has no
passphrase the agent can equally run `zssh connect` — or plain `ssh` — on its
own. What you get is a smaller credential surface and a deadline, not a
restriction on what the agent can do once it is on the box. See
[Security](#security).

## Lifetime

A session lasts one hour by default (`--ttl` to change it), timed from
`connect`, not from last use — a busy agent can't extend it indefinitely. A
small detached watchdog closes it exactly on time; `ControlPersist` is set to the
same TTL as a backstop, and any `zssh` command also reaps sessions that have
expired or whose master has died. `zssh close` ends one early.

## Completions

`./install.sh` links a zsh completion into `~/.zsh/completions`. If that
directory isn't already on your `fpath`, add this to `~/.zshrc` above any
existing `compinit`:

```sh
fpath=(~/.zsh/completions $fpath)
autoload -Uz compinit && compinit
```

For bash, source the script instead:

```sh
source /path/to/zssh/completions/zssh.bash
```

`install.sh` adds the `fpath` line to `~/.zshrc` for you (above your existing
`compinit`, with a `.zssh-backup` alongside). Set `ZSSH_NO_RC_EDIT=1` if you'd
rather wire it up yourself.

TAB then completes subcommands, flags, and **target names** — pulled live from
your address book, with their notes shown alongside:

```
$ zssh connect <TAB>
gpu   -- lab gpu
prod  -- prod web
```

`terminal`, `close` and `exec -t` complete only targets that actually have an
open session, so TAB won't offer you something you'd have to connect first.

`add` completes the *host* you're adding, gathered from `~/.ssh/config`,
unhashed `~/.ssh/known_hosts` entries, and your Tailscale peers when the
`tailscale` CLI is present (both the short name and the full MagicDNS name):

```
$ zssh add <TAB>
austins-mac-mini  austins-mac-mini.tail1d8ec6.ts.net  db1.internal  github.com
```

Set `ZSSH_TAILSCALE` to point at a non-standard `tailscale` binary, or to an
empty string to skip the tailnet lookup.

## Platform support

| Platform | Status | Notes |
| --- | --- | --- |
| macOS | Tested | Developed and end-to-end tested here (14/15, Apple's system Python 3.9, OpenSSH 10.3) |
| Linux | Expected to work | Same POSIX calls and same OpenSSH features; sockets go in `$XDG_RUNTIME_DIR` when set |
| BSD (FreeBSD/OpenBSD/NetBSD) | Expected to work | OpenSSH is native; nothing platform-specific beyond POSIX |
| WSL | Expected to work | It is Linux — use the WSL `ssh`, not `ssh.exe` |
| Windows (native) | **Not supported** | See below |

Honest labelling: "Tested" means I ran it against a real sshd; "Expected to
work" means the code paths are POSIX-standard and nothing in it is
macOS-specific, but I have not run it on that OS.

**Requirements:** Python **3.8+** (`shlex.join`) and OpenSSH **5.6+** (2010, for
`ControlPersist`). No third-party packages.

### Why Windows doesn't work

Not a rough edge — three independent blockers:

1. **Win32 OpenSSH does not implement connection multiplexing.** `ControlMaster`
   / `ControlPath` / `ControlPersist` are unsupported there, and they are the
   entire basis for a session that outlives the command that opened it.
2. **`os.execvp` doesn't replace a process on Windows.** The "shell opens in the
   same tab" behaviour comes from `zssh` *becoming* the ssh process; on Windows
   that call spawns a child and the parent exits.
3. **POSIX-only calls**: `os.getuid()` (used for the socket directory and the
   ownership check) doesn't exist on Windows, and `start_new_session` for the
   TTL watchdog is POSIX-only.

Use WSL, where all three are non-issues. Git Bash and MSYS2 generally shell out
to Win32 `ssh.exe`, so blocker 1 still applies.

### Cross-platform details worth knowing

- **Unix socket path limits** differ (~104 bytes on macOS/BSD, ~108 on Linux).
  `zssh` keeps sockets in `~/.zssh/s/` and falls back to a hashed name under
  `$XDG_RUNTIME_DIR` or `/tmp/zssh-$UID/` when the path would get close, so a
  long `$HOME` or a deep `ZSSH_HOME` won't break `connect`.
- **Case-insensitive filesystems** (macOS APFS/HFS+ by default, Windows NTFS):
  `prod` and `PROD` are two entries in the config but would share one socket
  and session file. `add` refuses such a pair rather than letting them collide;
  on case-sensitive Linux they would have been genuinely distinct.
- **Dropbear** (OpenWrt, some embedded/BusyBox systems) has no multiplexing
  client-side — `zssh` needs OpenSSH on the machine you run it *from*. The
  remote end can be anything, including Dropbear.
- **The remote OS is a separate question.** `exec` hands a command string to the
  target's login shell, which assumes a POSIX shell. A target whose default
  shell is `cmd.exe` or PowerShell will not honour POSIX quoting; point the
  account at a POSIX shell if you need `exec` there.

## Security

`zssh` stores no secrets of its own — authentication is ordinary OpenSSH (your
keys, your agent, your `~/.ssh/config`). `hosts.json` holds names, addresses,
ssh options and *paths* to keys, never key material or passwords. Files are
written `0600` and directories `0700`; if `~/.zssh` is found with looser modes,
it is tightened on the next run.

**The control socket is the sensitive object.** While a session is open,
anything that can talk to `~/.zssh/s/<name>.sock` reaches that host as you, with
no further authentication — that is exactly what makes `exec` fast and what
makes the socket worth protecting. Concretely:

- The socket directory is `0700` and verified on every run to be a real
  directory that you own and not a symlink; `zssh` refuses to use it otherwise.
  On a long `$HOME` the socket falls back to `/tmp/zssh-$UID/`, which lives in a
  world-writable directory, so that check is what stops another local user from
  pre-creating the path and inheriting your session.
- **Any process running as your UID can use an open session** — other shells,
  other tools, other agents. Unix permissions cannot separate you from yourself.
  If that matters, keep sessions short (`--ttl`) and close them when done.
- `root` on your machine can always reach it. Nothing here changes that.

**What an agent can and cannot do.** An agent with shell access and an open
session can run any command that account can run on the target — `zssh` adds no
allowlist, no sandbox, no confirmation. It bounds *duration*, not *authority*.
If the agent can also run `zssh connect` (your key is passphrase-less, or your
ssh-agent is unlocked), it can open sessions by itself, so restrict the agent's
own tool permissions if that is not what you want.

**Auditing.** Commands sent by `zssh exec` are non-interactive and do **not**
land in the remote shell history, so `~/.zsh_history` on the target will not
show what an agent did. `sshd` logs the session, not the individual commands.
If you need a per-command record, log it on the target (auditd, `pam_tty_audit`,
a forced-command wrapper) rather than relying on shell history.

**Host keys and forwarding.** Host key checking is whatever your ssh config
says — `zssh` never weakens it, and you should not pass
`-o StrictHostKeyChecking=no` on a host you care about, since multiplexing means
one accepted impostor serves every later `exec`. Agent forwarding is off unless
you add `-o ForwardAgent=yes`; forwarding your agent to a machine you don't
fully trust lets that machine use your keys.

**Sensible hardening for anything production-facing:**

- Give the agent a dedicated, least-privileged account rather than your own.
- Restrict what that key may do with `command=` / `ForceCommand` in
  `authorized_keys` on the target.
- Use a short `--ttl` (`zssh connect prod --ttl 900`) and `zssh close` when done.
- Keep `zssh status` in view — it tells you what is open and for how long.

Found a problem with any of this? Open an issue.

## Files

| Path | What |
| --- | --- |
| `~/.zssh/hosts.json` | your targets |
| `~/.zssh/sessions/*.json` | live session metadata (id, start, expiry) |
| `~/.zssh/s/*.sock` | SSH control sockets |
| `~/.zssh/current` | most recently connected target |

Set `ZSSH_HOME` to relocate all of it. (If that path is long, control sockets
fall back to `/tmp/zssh-$UID/` — unix sockets cap out around 104 bytes.)

## Tests

```sh
python3 -m unittest discover -s tests -v
```

The address-book and guard tests run anywhere. The end-to-end test connects to
`localhost` and skips itself if SSH to localhost isn't available.
