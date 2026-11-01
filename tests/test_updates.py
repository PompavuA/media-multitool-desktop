"""The 'new version on GitHub' check: version comparison, what GitHub's answer means, and what the page may ask for."""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ["MEDIA_DESKTOP_HOME"] = tempfile.mkdtemp(prefix="md-test-")

import app  # noqa: E402
import engine  # noqa: E402


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def answer(payload=None, error=None):
    def fake(req, timeout=None):
        if error:
            raise error
        return FakeResponse(json.dumps(payload).encode())
    return fake


class Versions(unittest.TestCase):
    def test_comparison(self):
        v = engine.version_tuple
        self.assertEqual((1, 2, 3), v("v1.2.3"))
        self.assertTrue(v("1.10.0") > v("1.9.9"))          # numbers, not text
        self.assertTrue(v("v2.0") > v("1.9.9"))
        self.assertEqual((1, 0, 1), v("v1.0.1-beta.2"))     # a tag suffix is ignored


class CheckOnGitHub(unittest.TestCase):
    def setUp(self):
        self._open = urllib.request.urlopen

    def tearDown(self):
        urllib.request.urlopen = self._open

    def test_newer_release_is_reported_with_its_page(self):
        urllib.request.urlopen = answer({"tag_name": "v1.1.0", "html_url": f"https://github.com/{engine.REPO}/releases/tag/v1.1.0"})
        self.assertEqual({"version": "1.1.0", "url": f"https://github.com/{engine.REPO}/releases/tag/v1.1.0"}, engine.check_app_update("1.0.0"))

    def test_small_fix_releases_stay_silent_but_feature_releases_show(self):
        for tag, shown in (("v1.0.1", False), ("v1.0.9", False), ("v1.1.0", True), ("v1.2.3", True), ("v2.0.0", True), ("v2", True)):
            urllib.request.urlopen = answer({"tag_name": tag})
            self.assertEqual(shown, engine.check_app_update("1.0.0") is not None, tag)
        urllib.request.urlopen = answer({"tag_name": "v1.1.5"})
        self.assertIsNone(engine.check_app_update("1.1.0"))      # already on 1.1: a later 1.1.x is only a small fix

    def test_same_older_draft_and_prerelease_are_ignored(self):
        for payload in ({"tag_name": "v1.0.0"}, {"tag_name": "v0.9.0"}, {"tag_name": "v2.0.0", "draft": True}, {"tag_name": "v2.0.0", "prerelease": True}, {}):
            urllib.request.urlopen = answer(payload)
            self.assertIsNone(engine.check_app_update("1.0.0"), payload)

    def test_no_release_yet_or_no_internet_is_just_silence(self):
        urllib.request.urlopen = answer(error=urllib.error.HTTPError("u", 404, "Not Found", {}, None))   # no release published yet
        self.assertIsNone(engine.check_app_update("1.0.0"))
        urllib.request.urlopen = answer(error=urllib.error.URLError("offline"))
        self.assertIsNone(engine.check_app_update("1.0.0"))
        urllib.request.urlopen = answer(error=TimeoutError())
        self.assertIsNone(engine.check_app_update("1.0.0"))


class WhatThePageMayAsk(unittest.TestCase):
    def setUp(self):
        self.api = app.Api()
        self._check, self._open = engine.check_app_update, app.webbrowser.open
        engine.check_app_update = lambda current: {"version": "1.1.0", "url": f"https://github.com/{engine.REPO}/releases/tag/v1.1.0"}

    def tearDown(self):
        engine.check_app_update, app.webbrowser.open = self._check, self._open

    def test_a_dismissed_version_is_not_shown_again_but_a_newer_one_is(self):
        self.assertEqual("1.1.0", self.api.check_app_update()["version"])
        self.api.dismiss_update("1.1.0")
        self.assertIsNone(self.api.check_app_update())
        engine.check_app_update = lambda current: {"version": "1.2.0", "url": f"https://github.com/{engine.REPO}/releases/latest"}
        self.assertEqual("1.2.0", self.api.check_app_update()["version"])

    def test_the_setting_switches_it_off_completely(self):
        self.api.set_pref("check_updates", False)
        engine.check_app_update = lambda current: self.fail("must not ask GitHub when the setting is off")
        self.assertIsNone(self.api.check_app_update())

    def test_only_this_repository_can_be_opened(self):
        opened = []
        app.webbrowser.open = opened.append
        self.api.open_url(f"https://github.com/{engine.REPO}/releases/latest")
        self.api.open_url("https://example.com/")
        self.api.open_url("https://github.com/someone-else/repo")
        file_url = "file:///C:/Windows/System32/calc.exe"
        self.api.open_url(file_url)
        self.assertEqual([f"https://github.com/{engine.REPO}/releases/latest"], opened)


if __name__ == "__main__":
    unittest.main()
