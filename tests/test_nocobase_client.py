"""Tests for the secret-safe NocoBase JSON client."""

import io
import json
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError

from features.nocobase_sync.config import NocoBaseConfig
from features.nocobase_sync.client import NocoBaseClient, NocoBaseError


class Response(io.BytesIO):
    def __init__(self, payload, status=200, headers=None):
        super().__init__(payload)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class NocoBaseClientTests(unittest.TestCase):
    def test_default_urlopen_receives_timeout_as_timeout_not_request_body(self):
        captured = []
        with mock.patch(
            "features.nocobase_sync.client.urlopen",
            side_effect=lambda request, **kwargs: captured.append((request, kwargs)) or Response(b'{"data":[]}'),
        ):
            client = NocoBaseClient(NocoBaseConfig("https://example.test", "token", True))
            client.request("campus_talent_pool:list")
        self.assertIsNone(captured[0][0].data)
        self.assertEqual(captured[0][1], {"timeout": 30})

    def test_swagger_document_accepts_raw_or_wrapped_json(self):
        responses = [Response(b'{"openapi":"3.0.0"}'), Response(b'{"data":{"openapi":"3.0.0"}}')]
        client = NocoBaseClient(
            NocoBaseConfig("https://example.test", "token", True),
            opener=lambda _request, _timeout: responses.pop(0),
        )
        self.assertEqual(client.request_document("swagger:get"), {"openapi":"3.0.0"})
        self.assertEqual(client.request_document("swagger:get"), {"openapi":"3.0.0"})

    def test_request_builds_api_url_bearer_header_and_json_body(self):
        captured = []

        def open_request(request, timeout):
            captured.append((request, timeout))
            return Response(b'{"data":{"id":7}}')

        client = NocoBaseClient(NocoBaseConfig("http://cloud.test:443", "top-secret", True), opener=open_request)
        result = client.request("campus_talent_pool:create", method="POST", body={"name": "API测试"})

        request, timeout = captured[0]
        self.assertEqual(request.full_url, "http://cloud.test:443/api/campus_talent_pool:create")
        self.assertEqual(request.get_header("Authorization"), "Bearer top-secret")
        self.assertEqual(json.loads(request.data), {"name": "API测试"})
        self.assertEqual(timeout, 30)
        self.assertEqual(result, {"id": 7})

    def test_existing_api_suffix_is_not_duplicated_and_empty_filter_is_omitted(self):
        urls = []
        client = NocoBaseClient(
            NocoBaseConfig("https://example.test/api/", "token", True),
            opener=lambda request, timeout: urls.append(request.full_url) or Response(b'{"data":1}'),
        )
        client.request("campus_talent_pool:update", method="POST",
                       params={"filterByTk": 12, "filter": {}, "unused": ""}, body={"name": "x"})
        self.assertEqual(urls, ["https://example.test/api/campus_talent_pool:update?filterByTk=12"])

    def test_status_errors_are_classified_without_exposing_api_key(self):
        for status, kind in ((400, "validation"), (401, "authentication"), (403, "permission"), (500, "remote")):
            with self.subTest(status=status):
                def fail(_request, _timeout, status=status):
                    raise HTTPError("https://example.test", status, "error", {}, io.BytesIO(b'{"secret":"body"}'))

                client = NocoBaseClient(NocoBaseConfig("https://example.test", "never-leak", True), opener=fail)
                with self.assertRaises(NocoBaseError) as raised:
                    client.request("campus_talent_pool:list")
                self.assertEqual((raised.exception.kind, raised.exception.status), (kind, status))
                self.assertNotIn("never-leak", str(raised.exception))
                self.assertNotIn("secret", str(raised.exception))

    def test_network_invalid_json_and_missing_data_are_rejected(self):
        fixtures = (
            (lambda _r, _t: (_ for _ in ()).throw(URLError("offline")), "network"),
            (lambda _r, _t: Response(b"not-json"), "protocol"),
            (lambda _r, _t: Response(b'{"meta":{}}'), "protocol"),
        )
        for opener, kind in fixtures:
            with self.subTest(kind=kind):
                client = NocoBaseClient(NocoBaseConfig("https://example.test", "token", True), opener=opener)
                with self.assertRaises(NocoBaseError) as raised:
                    client.request("campus_talent_pool:list")
                self.assertEqual(raised.exception.kind, kind)

    def test_disabled_configuration_never_opens_a_connection(self):
        client = NocoBaseClient(NocoBaseConfig("https://example.test", "token", False),
                               opener=lambda *_: self.fail("connection must not open"))
        with self.assertRaises(NocoBaseError) as raised:
            client.request("campus_talent_pool:list")
        self.assertEqual(raised.exception.kind, "disabled")

    def test_request_envelope_preserves_valid_meta(self):
        client = NocoBaseClient(
            NocoBaseConfig("https://example.test", "token", True),
            opener=lambda _r, _t: Response(b'{"data":[{"id":1}],"meta":{"count":9,"page":1}}'),
        )
        response = client.request_envelope("campus_talent_pool:list")
        self.assertEqual(response.data, [{"id": 1}])
        self.assertEqual(response.meta, {"count": 9, "page": 1})

    def test_request_envelope_rejects_non_object_meta(self):
        client = NocoBaseClient(
            NocoBaseConfig("https://example.test", "token", True),
            opener=lambda _r, _t: Response(b'{"data":[],"meta":[]}'),
        )
        with self.assertRaises(NocoBaseError) as raised:
            client.request_envelope("campus_talent_pool:list")
        self.assertEqual(raised.exception.kind, "protocol")

    def test_request_void_accepts_empty_success_response(self):
        captured = []
        client = NocoBaseClient(
            NocoBaseConfig("https://example.test", "token", True),
            opener=lambda request, timeout: captured.append((request, timeout)) or Response(b""),
        )
        self.assertIsNone(client.request_void(
            "Resume_Collection/1/Resume:set", params={"filterByTks": [2]},
        ))
        self.assertEqual(captured[0][0].method, "POST")
        self.assertIn("filterByTks=%5B2%5D", captured[0][0].full_url)
        self.assertIsNone(captured[0][0].data)

    def test_upload_builds_multipart_and_requires_integer_attachment_id(self):
        captured = []
        responses = [Response(b'{"data":{"id":31}}'), Response(b'{"data":{"title":"bad"}}')]
        client = NocoBaseClient(
            NocoBaseConfig("https://example.test", "top-secret", True),
            opener=lambda request, timeout: captured.append((request, timeout)) or responses.pop(0),
        )
        result = client.upload("attachments:create", filename="../简历.pdf", mime_type="application/pdf",
                               content=b"PDF-CONTENT", params={"attachmentField": "campus_talent_pool.biographical_notes"})
        self.assertEqual(result["id"], 31)
        request = captured[0][0]
        self.assertEqual(request.method, "POST")
        self.assertIn("attachmentField=campus_talent_pool.biographical_notes", request.full_url)
        self.assertTrue(request.get_header("Content-type").startswith("multipart/form-data; boundary="))
        self.assertIn("简历.pdf".encode("utf-8"), request.data)
        self.assertNotIn("../".encode(), request.data)
        self.assertIn(b"PDF-CONTENT", request.data)
        with self.assertRaises(NocoBaseError) as raised:
            client.upload("attachments:create", filename="bad.pdf", mime_type="application/pdf", content=b"x")
        self.assertEqual(raised.exception.kind, "protocol")
        self.assertNotIn("top-secret", str(raised.exception))

    def test_download_rejects_non_http_and_never_sends_credentials_cross_origin(self):
        requests = []
        client = NocoBaseClient(
            NocoBaseConfig("https://example.test", "top-secret", True),
            opener=lambda request, timeout: requests.append(request) or Response(
                b"file", headers={"Content-Type": "application/pdf"}),
        )
        self.assertEqual(client.download("https://example.test/files/a.pdf"), (b"file", "application/pdf"))
        self.assertEqual(requests[-1].get_header("Authorization"), "Bearer top-secret")
        self.assertEqual(client.download("https://cdn.example.net/a.pdf"), (b"file", "application/pdf"))
        self.assertIsNone(requests[-1].get_header("Authorization"))
        for value in ("file:///tmp/a.pdf", "https://user:pass@example.test/a", "https://example.test/a#part"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                client.download(value)

    def test_download_requires_enabled_configuration_and_normalizes_default_ports(self):
        disabled = NocoBaseClient(
            NocoBaseConfig("https://example.test", "token", False),
            opener=lambda *_: self.fail("connection must not open"),
        )
        with self.assertRaises(NocoBaseError) as raised:
            disabled.download("https://example.test/file.pdf")
        self.assertEqual(raised.exception.kind, "disabled")

        requests = []
        enabled = NocoBaseClient(
            NocoBaseConfig("https://example.test", "token", True),
            opener=lambda request, _timeout: requests.append(request) or Response(b"file"),
        )
        enabled.download("https://example.test:443/file.pdf")
        self.assertEqual(requests[-1].get_header("Authorization"), "Bearer token")

    def test_download_rejects_invalid_port(self):
        client = NocoBaseClient(NocoBaseConfig("https://example.test", "token", True))
        with self.assertRaises(ValueError):
            client.download("https://example.test:not-a-port/file.pdf")

    def test_download_enforces_maximum_bytes_while_reading(self):
        client = NocoBaseClient(
            NocoBaseConfig("https://example.test", "token", True),
            opener=lambda _request, _timeout: Response(b"12345"),
        )
        with self.assertRaisesRegex(ValueError, "大小"):
            client.download("https://example.test/file.pdf", maximum_bytes=4)
        self.assertEqual(
            client.download("https://example.test/file.pdf", maximum_bytes=5),
            (b"12345", "application/octet-stream"),
        )

    def test_upload_sanitizes_multipart_header_characters_in_filename(self):
        requests = []
        client = NocoBaseClient(
            NocoBaseConfig("https://example.test", "token", True),
            opener=lambda request, _timeout: requests.append(request) or Response(b'{"data":{"id":1}}'),
        )
        client.upload(
            "attachments:create",
            filename='resume"\r\nX-Injection: yes.pdf',
            mime_type="application/pdf",
            content=b"pdf",
        )
        disposition = requests[0].data.split(b"\r\n", 2)[1]
        self.assertNotIn(b"\r", disposition)
        self.assertNotIn(b"\n", disposition)
        self.assertNotIn(b'filename="resume"', disposition)


if __name__ == "__main__":
    unittest.main()
