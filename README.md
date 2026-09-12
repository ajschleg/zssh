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

Requires Python 3.8+ and OpenSSH — both already on macOS and most Linux boxes.

## Targets

```sh
zssh add prod deploy@10.0.0.7            # name -> address
zssh add gpu ubuntu@192.168.1.50:2222 -i ~/.ssh/lab_ed25519
zssh add jump root@203.0.113.9 -o StrictHostKeyChecking=no -d "bastion"
zssh list
zssh rm gpu
```

`add` takes `[user@]host[:port]`; `-u/-p/-i` override the pieces, `-o` passes any
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

It never handles a credential, it can't open a connection to anything you didn't
connect to yourself, and the blast radius is bounded by the TTL — after an hour
the session closes on its own even if nobody remembers to.

## Lifetime

A session lasts one hour by default (`--ttl` to change it), timed from
`connect`, not from last use — a busy agent can't extend it indefinitely. A
small detached watchdog closes it exactly on time; `ControlPersist` is set to the
same TTL as a backstop, and any `zssh` command also reaps sessions that have
expired or whose master has died. `zssh close` ends one early.

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
