"""Tests for the secret-safe NocoBase JSON client."""

import io
import json
import unittest
from urllib.error import HTTPError, URLError

from features.nocobase_sync.config import NocoBaseConfig
from features.nocobase_sync.client import NocoBaseClient, NocoBaseError


class Response(io.BytesIO):
    def __init__(self, payload, status=200):
        super().__init__(payload)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class NocoBaseClientTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
