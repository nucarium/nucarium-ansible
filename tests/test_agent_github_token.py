"""agent-github-token, as tests/render.yml renders it into out/render/, run
against a stand-in for GitHub and a folder of its own in place of
/run/agent-tokens.

Every token is asked for named repositories and named permissions, never for
all the GitHub App has; each file gets the token minted for its own
repositories; an environment with no repository to name gets no token; the
folder of an environment that is gone is removed; and one token GitHub
refuses leaves the others minted.

The script is the rendered one; the tokens it is to mint are given here, so
that the test does not depend on which settings were rendered last.
"""

import io
import json
import os
import stat
import sys
import tempfile
import types
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RENDERED = os.path.join(HERE, "..", "out", "render", "agent-github-token")


class Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@unittest.skipUnless(os.path.exists(RENDERED), "tests/render.yml has not rendered the minter")
class Minter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = os.path.join(self.tmp.name, "run")
        key = os.path.join(self.tmp.name, "key.pem")
        with open(key, "w") as f:
            f.write("not a key")
        # An environment that was on the box and is in the settings no more.
        gone = os.path.join(self.run_dir, "environments", "no-longer-here")
        os.makedirs(gone)
        with open(os.path.join(gone, "github"), "w") as f:
            f.write("its last token")
        with open(RENDERED) as f:
            source = f.read()
        source = source.replace("/run/agent-tokens", self.run_dir).replace("/etc/agent-broker/github-app.pem", key)
        self.minter = {"__name__": "agent_github_token"}
        exec(compile(source, RENDERED, "exec"), self.minter)
        # The host's token, and three environments': one with a repository
        # of its own, and one with none the App can be asked for, which had
        # a token before.
        self.minter["TOKENS"] = {
            "github": ["web", "api", "infra"],
            "environments/main/github": ["web", "api"],
            "environments/infra/github": ["infra"],
            "environments/elsewhere/github": [],
        }
        self.minter["ENVIRONMENTS"] = ["main", "infra", "elsewhere"]
        os.makedirs(os.path.join(self.run_dir, "environments", "elsewhere"))
        with open(os.path.join(self.run_dir, "environments", "elsewhere", "github"), "w") as f:
            f.write("a token from before")
        self.asked = []
        self.refused = set()
        self.unreachable = False
        self.addCleanup(setattr, urllib.request, "urlopen", urllib.request.urlopen)
        urllib.request.urlopen = self.urlopen
        real_jwt = sys.modules.get("jwt")
        sys.modules["jwt"] = types.SimpleNamespace(encode=lambda claims, pem, algorithm: "an-assertion")
        self.addCleanup(lambda: sys.modules.pop("jwt") if real_jwt is None else sys.modules.__setitem__("jwt", real_jwt))
        real_argv, real_stderr = sys.argv, sys.stderr
        sys.argv, sys.stderr = ["agent-github-token"], io.StringIO()
        self.addCleanup(lambda: (setattr(sys, "argv", real_argv), setattr(sys, "stderr", real_stderr)))

    def urlopen(self, request, timeout=None):
        if self.unreachable:
            raise urllib.error.URLError("no route to GitHub")
        body = json.loads(request.data)
        self.asked.append(body)
        if self.refused & set(body.get("repositories") or []):
            raise urllib.error.HTTPError(request.full_url, 422, "Unprocessable Entity", {},
                                         io.BytesIO(b'{"message": "not accessible to the installation"}'))
        return Answer(json.dumps({"token": "token for " + " ".join(body["repositories"])}).encode())

    def tokens(self):
        """Each token file under the folder, by its path in it."""
        found = {}
        for folder, _, files in os.walk(self.run_dir):
            for name in files:
                path = os.path.join(folder, name)
                with open(path) as f:
                    found[os.path.relpath(path, self.run_dir)] = f.read()
        return found

    def wanted(self):
        """The files the settings ask for, and each one's repositories."""
        return {name: repositories for name, repositories in self.minter["TOKENS"].items() if repositories}

    def test_every_token_names_its_repositories_and_permissions(self):
        self.assertEqual(self.minter["main"](), 0)
        self.assertEqual(len(self.asked), len(self.wanted()))
        for body in self.asked:
            self.assertTrue(body["repositories"], body)
            self.assertTrue(body["permissions"], body)
            self.assertFalse([name for name in body["repositories"] if "/" in name], body)

    def test_each_file_holds_the_token_for_its_own_repositories(self):
        self.assertEqual(self.minter["main"](), 0)
        self.assertEqual(self.tokens(),
                         {name: "token for " + " ".join(repositories) for name, repositories in self.wanted().items()})
        for name in self.wanted():
            mode = stat.S_IMODE(os.stat(os.path.join(self.run_dir, name)).st_mode)
            self.assertEqual(mode & 0o007, 0, name)

    def test_no_token_is_asked_for_with_no_repository_to_name(self):
        self.assertEqual(self.minter["main"](), 0)
        self.assertNotIn("environments/elsewhere/github", self.tokens())
        self.assertNotIn([], [body["repositories"] for body in self.asked])

    def test_the_folder_of_an_environment_that_is_gone_is_removed(self):
        self.minter["main"]()
        self.assertNotIn("no-longer-here", os.listdir(os.path.join(self.run_dir, "environments")))

    def test_a_refused_token_leaves_the_others_minted(self):
        self.refused = {"infra"}
        # 2: nothing to try again until the settings change.
        self.assertEqual(self.minter["main"](), 2)
        self.assertEqual(self.tokens(), {"environments/main/github": "token for web api"})
        self.assertIn("infra", sys.stderr.getvalue())

    def test_an_unreachable_github_is_tried_again(self):
        self.unreachable = True
        self.assertEqual(self.minter["main"](), 1)
        self.assertEqual(self.asked, [])

    def test_show_asks_nothing(self):
        sys.argv = ["agent-github-token", "--show"]
        real_stdout, sys.stdout = sys.stdout, io.StringIO()
        try:
            self.assertEqual(self.minter["main"](), 0)
            shown = json.loads(sys.stdout.getvalue())
        finally:
            sys.stdout = real_stdout
        self.assertEqual(self.asked, [])
        self.assertEqual(set(shown), set(self.minter["TOKENS"]))


if __name__ == "__main__":
    unittest.main()
