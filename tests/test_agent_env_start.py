"""agent-env-start, run as a container environment's unit runs it before the
container starts: it refuses to start when one of the nucleus's files the
container gets read-only is missing, a link or the wrong kind, and otherwise
lists each bare repository's hooks folder to mount read-only.

podman is a stand-in on PATH that says every image exists.
"""

import os
import stat
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "roles", "agent_servers", "files", "agent-env-start")


class AgentEnvStart(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.nucleus = os.path.join(root, "workspace")
        os.makedirs(os.path.join(self.nucleus, ".claude"))
        os.makedirs(os.path.join(self.nucleus, ".seeds"))
        os.makedirs(os.path.join(self.nucleus, ".repos", "web.git", "hooks"))
        for name in (".claude/settings.json", ".mcp.json", "AGENTS.md", "CLAUDE.md"):
            with open(os.path.join(self.nucleus, name), "w") as f:
                f.write("{}\n")
        bin_dir = os.path.join(root, "bin")
        os.makedirs(bin_dir)
        podman = os.path.join(bin_dir, "podman")
        with open(podman, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(podman, stat.S_IRWXU)
        self.env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ["PATH"])
        self.out = os.path.join(root, "volumes")

    def tearDown(self):
        self.tmp.cleanup()

    def run_start(self):
        return subprocess.run(
            ["bash", SCRIPT, "main", self.nucleus, self.out],
            env=self.env, capture_output=True, text=True,
        )

    def path(self, name):
        return os.path.join(self.nucleus, name)

    def assert_refused(self, name, why):
        done = self.run_start()
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn(f"{name} in the nucleus is {why}", done.stdout)
        self.assertFalse(os.path.exists(self.out))

    def test_lists_the_hooks_of_each_repository(self):
        done = self.run_start()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        hooks = self.path(".repos/web.git/hooks")
        with open(self.out) as f:
            self.assertEqual(f.read(), f"NUCARIUM_HOOK_VOLUMES=--volume={hooks}:{hooks}:ro\n")

    def test_skips_a_repository_whose_hooks_are_a_link(self):
        os.makedirs(self.path(".repos/odd.git"))
        os.symlink(self.path(".seeds"), self.path(".repos/odd.git/hooks"))
        done = self.run_start()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        with open(self.out) as f:
            self.assertNotIn("odd.git", f.read())

    def test_refuses_repos_as_a_link(self):
        elsewhere = os.path.join(self.tmp.name, "elsewhere")
        os.makedirs(os.path.join(elsewhere, "x.git", "hooks"))
        os.rename(self.path(".repos"), os.path.join(self.tmp.name, "repos-moved"))
        os.symlink(elsewhere, self.path(".repos"))
        self.assert_refused(".repos", "a link")

    def test_refuses_a_missing_claude_md(self):
        os.remove(self.path("CLAUDE.md"))
        self.assert_refused("CLAUDE.md", "missing")

    def test_refuses_mcp_json_as_a_link(self):
        os.remove(self.path(".mcp.json"))
        os.symlink(self.path("AGENTS.md"), self.path(".mcp.json"))
        self.assert_refused(".mcp.json", "a link")

    def test_refuses_a_missing_agents_md(self):
        os.remove(self.path("AGENTS.md"))
        self.assert_refused("AGENTS.md", "missing")

    def test_refuses_agents_md_as_a_link(self):
        os.remove(self.path("AGENTS.md"))
        os.symlink(self.path(".seeds"), self.path("AGENTS.md"))
        self.assert_refused("AGENTS.md", "a link")

    def test_refuses_a_link_to_a_file_where_settings_belong(self):
        os.remove(self.path(".claude/settings.json"))
        os.symlink(self.path("AGENTS.md"), self.path(".claude/settings.json"))
        self.assert_refused(".claude/settings.json", "a link")

    def test_refuses_a_missing_claude_folder(self):
        os.remove(self.path(".claude/settings.json"))
        os.rmdir(self.path(".claude"))
        self.assert_refused(".claude", "missing")

    def test_refuses_a_file_where_seeds_belong(self):
        os.rmdir(self.path(".seeds"))
        with open(self.path(".seeds"), "w") as f:
            f.write("")
        self.assert_refused(".seeds", "not a folder")

    def test_refuses_a_folder_where_agents_md_belongs(self):
        os.remove(self.path("AGENTS.md"))
        os.makedirs(self.path("AGENTS.md"))
        self.assert_refused("AGENTS.md", "not a file")


if __name__ == "__main__":
    unittest.main()
