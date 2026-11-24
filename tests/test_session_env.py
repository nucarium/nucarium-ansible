"""session-env.sh, run as a session's SessionStart hook runs it: the lines it
appends to CLAUDE_ENV_FILE, sourced by bash as the session sources them,
give the session a GitHub token in GH_TOKEN and GITHUB_TOKEN.

Where the GitHub App's token cannot be read (here, and in a container
environment with a GitHub identity of its own), a GITHUB_TOKEN the session
already has is kept, and GH_TOKEN is the same. With none, both are empty.
"""

import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "roles", "claude", "files", "session-env.sh")
APP_TOKEN = "/run/agent-tokens/github"


@unittest.skipIf(os.access(APP_TOKEN, os.R_OK), "the GitHub App's token is readable here")
class SessionEnv(unittest.TestCase):
    def tokens(self, **given):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = os.path.join(tmp, "env")
            env = {"PATH": os.environ["PATH"], "HOME": tmp, "CLAUDE_ENV_FILE": env_file}
            env.update(given)
            hook = subprocess.run(["bash", SCRIPT, "main"], env=env, capture_output=True, text=True)
            self.assertEqual(hook.returncode, 0, hook.stderr)
            env.pop("CLAUDE_ENV_FILE")
            shown = subprocess.run(
                ["bash", "-c", '. "$1"; printf \'{"GH_TOKEN": "%s", "GITHUB_TOKEN": "%s"}\' "$GH_TOKEN" "$GITHUB_TOKEN"',
                 "bash", env_file],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(shown.returncode, 0, shown.stderr)
            return json.loads(shown.stdout)

    def test_keeps_an_own_github_token(self):
        self.assertEqual(self.tokens(GITHUB_TOKEN="own-token"),
                         {"GH_TOKEN": "own-token", "GITHUB_TOKEN": "own-token"})

    def test_both_empty_with_no_token(self):
        self.assertEqual(self.tokens(), {"GH_TOKEN": "", "GITHUB_TOKEN": ""})

    def test_an_empty_github_token_is_no_token(self):
        self.assertEqual(self.tokens(GITHUB_TOKEN="", GH_TOKEN="stale"),
                         {"GH_TOKEN": "", "GITHUB_TOKEN": ""})


if __name__ == "__main__":
    unittest.main()
