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

    def test_duplicate_needs_force(self):
        self.zssh("add", "box", "1.2.3.4")
        dup = self.zssh("add", "box", "5.6.7.8")
        self.assertNotEqual(dup.returncode, 0)
        self.assertIn("already exists", dup.stderr)
        self.assertEqual(self.zssh("add", "box", "5.6.7.8", "--force").returncode, 0)
        self.assertEqual(json.loads(self.zssh("list", "--json").stdout)["box"]["host"], "5.6.7.8")

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

        status = json.loads(self.zssh("status", "--json").stdout)
        self.assertEqual(status[0]["name"], "local")

        self.assertEqual(self.zssh("close", "local").returncode, 0)
        self.assertNotEqual(self.zssh("exec", "-t", "local", "true").returncode, 0)


if __name__ == "__main__":
    unittest.main()
