"""Tests for zssh.

The config/session-bookkeeping tests run anywhere. The end-to-end test only
runs if this machine can ssh to localhost without a prompt (macOS: System
Settings > General > Sharing > Remote Login), which is the cheapest real
target for exercising the multiplexed session.
"""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin" / "zssh"

spec = importlib.util.spec_from_loader("zssh", importlib.machinery.SourceFileLoader("zssh", str(BIN)))
zssh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(zssh)


def localhost_ssh_works():
    if shutil.which("ssh") is None:
        return False
    try:
        return subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
             "-o", "ConnectTimeout=5", "localhost", "true"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20).returncode == 0
    except Exception:
        return False


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="zssh-test-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.env = dict(os.environ, ZSSH_HOME=self.home)

    def zssh(self, *args, **kwargs):
        return subprocess.run([sys.executable, str(BIN), *args], env=self.env,
                              capture_output=True, text=True, **kwargs)


class TestHostBook(CliTestCase):
    def test_add_list_remove(self):
        out = self.zssh("add", "web", "deploy@10.0.0.7:2222", "-d", "prod web")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("deploy@10.0.0.7", out.stdout)

        listed = json.loads(self.zssh("list", "--json").stdout)
        self.assertEqual(listed["web"]["host"], "10.0.0.7")
        self.assertEqual(listed["web"]["user"], "deploy")
        self.assertEqual(listed["web"]["port"], 2222)
        self.assertEqual(listed["web"]["status"], "offline")

        plain = self.zssh("list").stdout
        self.assertIn("prod web", plain)

        self.assertEqual(self.zssh("rm", "web").returncode, 0)
        self.assertEqual(json.loads(self.zssh("list", "--json").stdout), {})

    def test_add_without_a_name_derives_one_from_the_host(self):
        out = self.zssh("add", "austinschlegel@austins-mac-mini.tail1d8ec6.ts.net")
        self.assertEqual(out.returncode, 0, out.stderr)
        entry = json.loads(self.zssh("list", "--json").stdout)["austins-mac-mini"]
        self.assertEqual(entry["host"], "austins-mac-mini.tail1d8ec6.ts.net")
        self.assertEqual(entry["user"], "austinschlegel")

    def test_derived_name_handles_plain_hostnames_and_ports(self):
        self.zssh("add", "db1.internal.example.com:2222")
        entry = json.loads(self.zssh("list", "--json").stdout)["db1"]
        self.assertEqual(entry["host"], "db1.internal.example.com")
        self.assertEqual(entry["port"], 2222)
        self.assertNotIn("user", entry)

    def test_bare_ip_requires_an_explicit_name(self):
        res = self.zssh("add", "10.0.0.9")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("cannot derive a name", res.stderr)
        self.assertEqual(self.zssh("add", "box", "10.0.0.9").returncode, 0)

    def test_duplicate_needs_force(self):
        self.zssh("add", "box", "1.2.3.4")
        dup = self.zssh("add", "box", "5.6.7.8")
        self.assertNotEqual(dup.returncode, 0)
        self.assertIn("already exists", dup.stderr)
        self.assertEqual(self.zssh("add", "box", "5.6.7.8", "--force").returncode, 0)
        self.assertEqual(json.loads(self.zssh("list", "--json").stdout)["box"]["host"], "5.6.7.8")

    def test_rejects_case_only_collision(self):
        # Two such names are distinct JSON keys but one socket file on APFS/NTFS.
        self.zssh("add", "prod", "10.0.0.1")
        res = self.zssh("add", "PROD", "10.0.0.2")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("collides", res.stderr)
        self.assertEqual(self.zssh("__targets").stdout.split(), ["prod"])

    def test_rejects_bad_name_and_port(self):
        self.assertNotEqual(self.zssh("add", "bad name", "1.2.3.4").returncode, 0)
        self.assertNotEqual(self.zssh("add", "ok", "1.2.3.4:http").returncode, 0)

    def test_identity_and_options_are_stored(self):
        self.zssh("add", "k", "1.2.3.4", "-i", "~/.ssh/id_ed25519",
                  "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5")
        entry = json.loads(self.zssh("list", "--json").stdout)["k"]
        self.assertEqual(entry["identity"], "~/.ssh/id_ed25519")
        self.assertEqual(entry["options"], ["StrictHostKeyChecking=no", "ConnectTimeout=5"])


class TestSessionGuards(CliTestCase):
    def test_commands_require_a_session(self):
        self.zssh("add", "box", "1.2.3.4")
        for args in (("exec", "-t", "box", "ls"), ("terminal", "box")):
            res = self.zssh(*args)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("no active session", res.stderr)

    def test_exec_without_target_and_without_sessions(self):
        res = self.zssh("exec", "ls")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("no active sessions", res.stderr)

    def test_unknown_target(self):
        res = self.zssh("connect", "nope")
        self.assertIn("unknown target", res.stderr)

    def test_status_empty(self):
        self.assertEqual(self.zssh("status").stdout.strip(), "no active sessions")


class TestUnits(unittest.TestCase):
    def test_parse_destination(self):
        self.assertEqual(zssh.parse_destination("1.2.3.4"), (None, "1.2.3.4", None))
        self.assertEqual(zssh.parse_destination("bob@1.2.3.4"), ("bob", "1.2.3.4", None))
        self.assertEqual(zssh.parse_destination("bob@1.2.3.4:2222"), ("bob", "1.2.3.4", 2222))
        self.assertEqual(zssh.parse_destination("[::1]:22"), (None, "::1", 22))
        self.assertEqual(zssh.parse_destination("2001:db8::1"), (None, "2001:db8::1", None))

    def test_human_duration(self):
        self.assertEqual(zssh.human_duration(3600), "1h00m")
        self.assertEqual(zssh.human_duration(90), "1m30s")
        self.assertEqual(zssh.human_duration(-5), "0s")


class TestCompletionSupport(CliTestCase):
    """The completion scripts shell out to `zssh __targets`; keep it stable."""

    def test_targets_lists_names_only(self):
        self.zssh("add", "prod", "deploy@10.0.0.7", "-d", "prod web")
        self.zssh("add", "gpu", "ubuntu@192.168.1.50:2222")
        self.assertEqual(self.zssh("__targets").stdout.split(), ["gpu", "prod"])

    def test_targets_describe_is_tab_separated(self):
        self.zssh("add", "prod", "deploy@10.0.0.7", "-d", "prod web")
        line = self.zssh("__targets", "--describe").stdout.strip()
        self.assertEqual(line, "prod\tprod web")

    def test_targets_describe_falls_back_to_address(self):
        self.zssh("add", "gpu", "ubuntu@192.168.1.50:2222")
        self.assertEqual(self.zssh("__targets", "--describe").stdout.strip(),
                         "gpu\tubuntu@192.168.1.50:2222")

    def test_live_filter_is_empty_without_sessions(self):
        self.zssh("add", "prod", "deploy@10.0.0.7")
        self.assertEqual(self.zssh("__targets", "--live").stdout.strip(), "")

    def test_targets_skips_malformed_names(self):
        Path(self.home).mkdir(parents=True, exist_ok=True)
        (Path(self.home) / "hosts.json").write_text(json.dumps(
            {"version": 1, "hosts": {"ok": {"host": "1.2.3.4"},
                                     "../bad": {"host": "5.6.7.8"}}}))
        self.assertEqual(self.zssh("__targets").stdout.split(), ["ok"])


class TestDestinationDiscovery(CliTestCase):
    """`zssh __destinations` feeds completion for `add`; it must never crash."""

    def fake_home(self, config=None, known=None):
        fake = tempfile.mkdtemp(prefix="zssh-home-")
        self.addCleanup(shutil.rmtree, fake, True)
        ssh = Path(fake) / ".ssh"
        ssh.mkdir()
        if config is not None:
            (ssh / "config").write_text(config)
        if known is not None:
            (ssh / "known_hosts").write_text(known)
        env = dict(self.env, HOME=fake, ZSSH_TAILSCALE="")  # skip tailnet lookup
        return env

    def run_dests(self, env):
        res = subprocess.run([sys.executable, str(BIN), "__destinations"],
                             env=env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout.split()

    def test_reads_ssh_config_and_skips_wildcards(self):
        env = self.fake_home(config="Host web1 web2\n  User deploy\nHost *.internal\nHost *\n")
        out = self.run_dests(env)
        self.assertIn("web1", out)
        self.assertIn("web2", out)
        self.assertNotIn("*", out)
        self.assertNotIn("*.internal", out)

    def test_reads_known_hosts_and_skips_hashed_entries(self):
        env = self.fake_home(known=(
            "example.com ssh-ed25519 AAAA\n"
            "[10.0.0.5]:2222 ssh-rsa BBBB\n"
            "alpha.local,10.0.0.6 ssh-ed25519 CCCC\n"
            "|1|hashedsalt=|hashedhost= ssh-ed25519 DDDD\n"))
        out = self.run_dests(env)
        self.assertIn("example.com", out)
        self.assertIn("10.0.0.5", out)   # port stripped from [host]:port
        self.assertIn("alpha.local", out)
        self.assertIn("10.0.0.6", out)
        self.assertFalse([x for x in out if x.startswith("|")])

    def test_survives_missing_files(self):
        self.assertEqual(self.run_dests(self.fake_home()), [])

    def test_output_is_sorted_and_deduplicated(self):
        env = self.fake_home(config="Host dup\nHost alpha\n", known="dup ssh-ed25519 AAAA\n")
        out = self.run_dests(env)
        self.assertEqual(out, sorted(out))
        self.assertEqual(len(out), len(set(out)))


class TestCompletionScripts(unittest.TestCase):
    def test_zsh_completion_parses(self):
        if shutil.which("zsh") is None:
            self.skipTest("zsh not available")
        res = subprocess.run(["zsh", "-n", str(ROOT / "completions" / "_zssh")],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_bash_completion_parses(self):
        res = subprocess.run(["bash", "-n", str(ROOT / "completions" / "zssh.bash")],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_completions_use_the_hidden_helpers(self):
        zsh_src = (ROOT / "completions" / "_zssh").read_text()
        bash_src = (ROOT / "completions" / "zssh.bash").read_text()
        for src in (zsh_src, bash_src):
            self.assertIn("__targets", src)
            self.assertIn("__destinations", src)

    def test_every_command_appears_in_both_completions(self):
        zsh_src = (ROOT / "completions" / "_zssh").read_text()
        bash_src = (ROOT / "completions" / "zssh.bash").read_text()
        for cmd in ("add", "remove", "rm", "list", "ls", "connect",
                    "terminal", "term", "exec", "close", "status", "config-path"):
            self.assertIn(cmd, zsh_src, "%s missing from zsh completion" % cmd)
            self.assertIn(cmd, bash_src, "%s missing from bash completion" % cmd)


class TestHardening(CliTestCase):
    def test_hand_edited_config_cannot_escape_the_config_dir(self):
        # Names are used to build socket/session paths, so a traversal name in a
        # hand-edited config must be refused rather than written through.
        Path(self.home).mkdir(parents=True, exist_ok=True)
        (Path(self.home) / "hosts.json").write_text(json.dumps(
            {"version": 1, "hosts": {"../../evil": {"host": "1.2.3.4"}}}))
        res = self.zssh("connect", "../../evil")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("invalid target name", res.stderr)

    def test_loose_permissions_are_tightened(self):
        os.chmod(self.home, 0o755)
        self.zssh("add", "box", "1.2.3.4")
        self.assertEqual(os.stat(self.home).st_mode & 0o777, 0o700)
        for sub in ("sessions", "s"):
            self.assertEqual(os.stat(os.path.join(self.home, sub)).st_mode & 0o777, 0o700)

    def test_config_is_not_world_readable(self):
        self.zssh("add", "box", "1.2.3.4")
        self.assertEqual(os.stat(os.path.join(self.home, "hosts.json")).st_mode & 0o077, 0)


class TestSecureDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="zssh-secdir-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_rejects_symlinked_directory(self):
        real = Path(self.tmp) / "real"
        real.mkdir()
        link = Path(self.tmp) / "link"
        link.symlink_to(real)
        with self.assertRaises(SystemExit):
            zssh.secure_dir(link)

    def test_rejects_non_directory(self):
        f = Path(self.tmp) / "afile"
        f.write_text("x")
        with self.assertRaises(SystemExit):
            zssh.secure_dir(f)

    def test_creates_private_and_tightens_existing(self):
        fresh = Path(self.tmp) / "fresh"
        zssh.secure_dir(fresh)
        self.assertEqual(os.stat(fresh).st_mode & 0o777, 0o700)
        os.chmod(fresh, 0o777)
        zssh.secure_dir(fresh)
        self.assertEqual(os.stat(fresh).st_mode & 0o777, 0o700)


@unittest.skipUnless(localhost_ssh_works(), "ssh to localhost is not available")
class TestLiveSession(CliTestCase):
    def test_connect_exec_close(self):
        self.zssh("add", "local", "localhost", "-o", "StrictHostKeyChecking=no",
                  "-o", "BatchMode=yes")
        connected = self.zssh("connect", "local", "--detach", "--ttl", "120")
        self.assertEqual(connected.returncode, 0, connected.stderr)

        run = self.zssh("exec", "echo", "hello from zssh")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "hello from zssh")

        # Remote exit codes propagate.
        self.assertEqual(self.zssh("exec", "exit 7").returncode, 7)

        # The session is shared: state written by one exec is visible to the next.
        self.zssh("exec", "echo persisted > /tmp/zssh-live-test")
        self.assertEqual(self.zssh("exec", "cat /tmp/zssh-live-test").stdout.strip(), "persisted")
        self.zssh("exec", "rm -f /tmp/zssh-live-test")

        # The interactive shell gets a `zssh@<target>` prompt via the shim.
        import pty, re
        def interactive(args, line):
            chunks, inp = [], [line, b"exit\n"]
            def rd(fd):
                d = os.read(fd, 8192); chunks.append(d); return d
            def wr(fd):
                return inp.pop(0) if inp else b""
            pty.spawn([sys.executable, str(BIN)] + args, rd, wr)
            return re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b[=>]|\r", "",
                          b"".join(chunks).decode(errors="replace"))

        env_backup = os.environ.get("ZSSH_HOME")
        os.environ["ZSSH_HOME"] = self.home
        try:
            out = interactive(["terminal", "local"], b"true\n")
            self.assertIn("zssh@local", out)
            plain = interactive(["terminal", "local", "--no-prompt"], b"true\n")
            self.assertNotIn("zssh@local", plain)
        finally:
            if env_backup is None:
                os.environ.pop("ZSSH_HOME", None)
            else:
                os.environ["ZSSH_HOME"] = env_backup

        # No shim directories left behind on the remote.
        left = self.zssh("exec", 'ls -d "${TMPDIR:-/tmp}"/zssh.* 2>/dev/null | wc -l')
        self.assertEqual(left.stdout.strip(), "0")

        status = json.loads(self.zssh("status", "--json").stdout)
        self.assertEqual(status[0]["name"], "local")

        self.assertEqual(self.zssh("close", "local").returncode, 0)
        self.assertNotEqual(self.zssh("exec", "-t", "local", "true").returncode, 0)


if __name__ == "__main__":
    unittest.main()
