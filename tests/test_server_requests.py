"""The pieces a write from the UI goes through: form fields and the origin guard.

The routes themselves need an HTTP client to exercise, but these two functions
decide whether a post is read at all and whether it is acted on, so they are
worth pinning down on their own.
"""

import unittest

from fastapi import HTTPException
from starlette.requests import Request

from crodl.server.app import check_same_origin, edit_mode_on, form_fields, local_target


def request_with(
    body: bytes = b"",
    content_type: str = "application/x-www-form-urlencoded",
    host: str = "127.0.0.1:8000",
    origin: str | None = None,
    cookie: str | None = None,
) -> Request:
    """A minimal POST request, the way Starlette hands it to a route."""
    headers = [
        (b"host", host.encode()),
        (b"content-type", content_type.encode()),
        (b"content-length", str(len(body)).encode()),
    ]
    if origin is not None:
        headers.append((b"origin", origin.encode()))
    if cookie is not None:
        headers.append((b"cookie", cookie.encode()))

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/detail/series/s-1/edit",
        "raw_path": b"/detail/series/s-1/edit",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 12345),
    }

    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


class TestFormFields(unittest.IsolatedAsyncioTestCase):
    async def test_urlencoded_fields_are_read_and_decoded(self):
        request = request_with(b"title=D%C3%ADl+prvn%C3%AD&description=")

        self.assertEqual(
            await form_fields(request), {"title": "Díl první", "description": ""}
        )

    async def test_an_empty_form_gives_no_fields(self):
        self.assertEqual(await form_fields(request_with()), {})

    async def test_a_body_that_is_not_a_form_is_refused(self):
        request = request_with(b'{"title": "x"}', content_type="application/json")

        with self.assertRaises(HTTPException) as caught:
            await form_fields(request)

        self.assertEqual(caught.exception.status_code, 400)


class TestSameOriginGuard(unittest.TestCase):
    """A form posts where it likes, so writes check where they came from."""

    def test_a_form_from_this_server_passes(self):
        check_same_origin(
            request_with(origin="http://127.0.0.1:8000", host="127.0.0.1:8000")
        )

    def test_the_server_may_run_on_another_port(self):
        # Comparing against a configured port would lock the UI out here.
        check_same_origin(
            request_with(origin="http://127.0.0.1:8130", host="127.0.0.1:8130")
        )

    def test_localhost_is_localhost_too(self):
        check_same_origin(
            request_with(origin="http://localhost:8000", host="localhost:8000")
        )

    def test_a_stranger_origin_is_refused(self):
        with self.assertRaises(HTTPException) as caught:
            check_same_origin(request_with(origin="http://evil.example"))

        self.assertEqual(caught.exception.status_code, 403)

    def test_a_name_that_only_resolves_here_is_refused(self):
        # DNS rebinding: a page on evil.example, served from 127.0.0.1.
        with self.assertRaises(HTTPException):
            check_same_origin(
                request_with(origin="http://evil.example", host="evil.example")
            )

    def test_a_request_without_an_origin_passes(self):
        # curl and the test suite do not send one; the host check still applies.
        check_same_origin(request_with())

    def test_a_request_addressed_elsewhere_is_refused(self):
        with self.assertRaises(HTTPException):
            check_same_origin(request_with(host="192.168.1.10:8000"))


class TestLocalTarget(unittest.TestCase):
    """Where the edit-mode switch may send the browser."""

    def test_a_page_on_this_server_is_kept(self):
        self.assertEqual(local_target("/detail/series/s-1"), "/detail/series/s-1")

    def test_anything_else_goes_to_the_library(self):
        # The switch takes its destination from a query string, so it must not
        # turn into an open redirect.
        self.assertEqual(local_target("http://evil.example/"), "/")
        self.assertEqual(local_target("//evil.example/"), "/")
        self.assertEqual(local_target(""), "/")


class TestEditMode(unittest.TestCase):
    def test_editing_is_off_unless_the_cookie_turns_it_on(self):
        self.assertFalse(edit_mode_on(request_with()))
        self.assertFalse(edit_mode_on(request_with(cookie="edit=0")))
        self.assertTrue(edit_mode_on(request_with(cookie="edit=1")))


if __name__ == "__main__":
    unittest.main()
