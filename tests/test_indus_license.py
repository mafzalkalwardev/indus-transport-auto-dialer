"""Tests for INDUS license verification helpers."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.indus_license import (
    LicenseRecord,
    find_license_file,
    load_license,
    local_expired,
    verify_license,
)


class IndusLicenseTests(unittest.TestCase):
    def test_load_license_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "indus-license-dialer.json")
            payload = {
                "product": "Auto Dialer",
                "productSlug": "dialer-multi-slot",
                "expiresAt": "2099-01-01T00:00:00.000Z",
                "licenseToken": "abc.def.ghi",
                "verifyUrl": "https://example.com/api/license/verify",
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            record = load_license(path)
            self.assertEqual(record.product_slug, "dialer-multi-slot")
            self.assertEqual(record.license_token, "abc.def.ghi")

    def test_find_license_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(find_license_file(tmp))
            path = os.path.join(tmp, "indus-license-test.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"licenseToken": "x"}, f)
            self.assertEqual(find_license_file(tmp), path)

    def test_local_expired(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.assertTrue(local_expired(past))
        self.assertFalse(local_expired(future))

    @patch.dict(os.environ, {"INDUS_SKIP_LICENSE": "1"})
    def test_skip_license_check(self):
        result = verify_license("/nonexistent")
        self.assertTrue(result.ok)
        self.assertEqual(result.reason, "skipped")

    def test_missing_license(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"INDUS_SKIP_LICENSE": ""}, clear=False):
                result = verify_license(tmp)
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "missing")


if __name__ == "__main__":
    unittest.main()
