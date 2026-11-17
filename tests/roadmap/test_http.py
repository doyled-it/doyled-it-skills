"""The Forgejo HTTPS transport: token safety, redirects, pagination and the write guard.

These tests drive the real request code with a fake opener, so they exercise the
paths that send, refuse or could print a token.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
import urllib.error
import urllib.request
from unittest import mock

from helpers import example
from roadmaplib import forge, validate

TOKEN = "s3cret-token-value"


class Response:
    def __init__(self, body, headers=None):
        self.body = json.dumps(body).encode()
        self.headers = headers or {}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Records each request; answers from a list of results (a Response or an exception)."""

    def __init__(self, *results):
        self.results = list(results)
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append(req)
        result = self.results.pop(0) if self.results else Response([])
        if isinstance(result, Exception):
            raise result
        return result


def transport(host, *results):
    t = forge.HttpTransport(host)
    t._opener = FakeOpener(*results)
    return t


def auth(req):
    return req.get_header("Authorization")


class TokenGoesOnlyToItsHost(unittest.TestCase):
    def test_codeberg_token_goes_only_to_codeberg(self):
        with mock.patch.dict("os.environ", {"CODEBERG_TOKEN": TOKEN}, clear=True):
            t = transport("codeberg.org", Response({}))
            t.get("repos/o/r/issues/1")
            self.assertEqual(auth(t._opener.requests[0]), "token " + TOKEN)
            t = transport("attacker.example", Response({}))
            t.get("repos/o/r/issues/1")
            self.assertIsNone(auth(t._opener.requests[0]))

    def test_forgejo_token_needs_its_host_named_outside_the_roadmap(self):
        with mock.patch.dict("os.environ", {"FORGEJO_TOKEN": TOKEN}, clear=True):
            t = transport("git.example.org", Response({}))
            t.get("x")
            self.assertIsNone(auth(t._opener.requests[0]))
        with mock.patch.dict("os.environ", {"FORGEJO_TOKEN": TOKEN, "FORGEJO_HOST": "git.example.org"}, clear=True):
            t = transport("git.example.org", Response({}))
            t.get("x")
            self.assertEqual(auth(t._opener.requests[0]), "token " + TOKEN)
            t = transport("attacker.example", Response({}))
            t.get("x")
            self.assertIsNone(auth(t._opener.requests[0]))

    def test_requests_use_https(self):
        t = transport("codeberg.org", Response({}))
        t.get("repos/o/r")
        self.assertTrue(t._opener.requests[0].full_url.startswith("https://codeberg.org/api/v1/"))

    def test_the_host_must_be_a_bare_host_name(self):
        for bad in ("http://codeberg.org", "codeberg.org/evil", "user@codeberg.org", "codeberg.org?x", "a b"):
            with self.subTest(bad=bad), self.assertRaises(forge.ForgeError):
                forge.HttpTransport(bad)
        forge.HttpTransport("git.example.org:3000")

    def test_validate_rejects_a_host_that_is_not_bare(self):
        data = example()
        data["forge"]["host"] = "https://github.com/x"
        self.assertIn("bad-forge", {f.code for f in validate.errors(validate.check(data))})


class TokenIsNeverPrinted(unittest.TestCase):
    def test_no_output_and_no_error_text_carries_the_token(self):
        failures = [Response({"ok": True}),
                    urllib.error.HTTPError("https://codeberg.org/api/v1/x", 500, "boom " + TOKEN, {}, io.BytesIO()),
                    urllib.error.URLError("refused " + TOKEN),
                    urllib.error.HTTPError("https://codeberg.org/api/v1/x", 404, "nope", {}, io.BytesIO())]
        with mock.patch.dict("os.environ", {"CODEBERG_TOKEN": TOKEN}, clear=True):
            t = transport("codeberg.org", *failures)
            out, err = io.StringIO(), io.StringIO()
            messages = []
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                t.get("x")
                for _ in range(3):
                    try:
                        t.get("x")
                    except forge.ForgeError as exc:
                        messages.append(str(exc) + repr(exc))
            self.assertEqual(len(messages), 3)
            for text in [out.getvalue(), err.getvalue(), *messages, repr(t), str(vars(t))]:
                self.assertNotIn(TOKEN, text)


class RedirectsStayOnTheHost(unittest.TestCase):
    def redirect(self, t, url):
        req = urllib.request.Request("https://codeberg.org/api/v1/x", headers={"Authorization": "token x"})
        return t._redirects.redirect_request(req, None, 302, "Found", {}, url)

    def test_redirects_to_another_host_or_to_http_are_refused(self):
        t = forge.HttpTransport("codeberg.org")
        for url in ("https://attacker.example/api/v1/x", "http://codeberg.org/api/v1/x",
                    "https://codeberg.org.attacker.example/x", "https://codeberg.org:8443/x"):
            with self.subTest(url=url), self.assertRaises(forge.ForgeError):
                self.redirect(t, url)

    def test_a_redirect_on_the_same_host_is_followed(self):
        t = forge.HttpTransport("codeberg.org")
        self.assertIsNotNone(self.redirect(t, "https://codeberg.org/api/v1/repos/o/renamed"))

    def test_the_opener_uses_the_checking_redirect_handler(self):
        t = forge.HttpTransport("codeberg.org")
        handlers = [h for h in t._opener.handlers if isinstance(h, urllib.request.HTTPRedirectHandler)]
        self.assertEqual(handlers, [t._redirects])


class Pagination(unittest.TestCase):
    def test_total_count_header_is_followed_when_pages_are_small(self):
        pages = [Response(list(range(30)), {"X-Total-Count": "70"}),
                 Response(list(range(30, 60)), {"X-Total-Count": "70"}),
                 Response(list(range(60, 70)), {"X-Total-Count": "70"})]
        self.assertEqual(transport("codeberg.org", *pages).get_all("repos/o/r/issues"), list(range(70)))

    def test_without_a_header_it_reads_until_an_empty_page(self):
        pages = [Response(list(range(30))), Response(list(range(30, 60))), Response(list(range(60, 70))),
                 Response([])]
        self.assertEqual(transport("codeberg.org", *pages).get_all("repos/o/r/issues"), list(range(70)))


class WriteGuardRunsBeforeTheNetwork(unittest.TestCase):
    def test_close_and_delete_never_reach_the_forge(self):
        t = transport("codeberg.org")
        for method, body in (("DELETE", None), ("PATCH", {"state": "closed"}), ("PATCH", {"title": "a\nb"})):
            with self.subTest(method=method, body=body), self.assertRaises(forge.ForgeError):
                t.send(method, "repos/o/r/issues/1", body)
        self.assertEqual(t._opener.requests, [])


if __name__ == "__main__":
    unittest.main()
