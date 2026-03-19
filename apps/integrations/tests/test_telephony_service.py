import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.integrations.services.telephony_service import download_call_record_detailed


class TelephonyServiceTests(SimpleTestCase):
    def test_download_call_record_detailed_supports_file_scheme(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "call.mp3"
            p.write_bytes(b"FAKE")
            result = download_call_record_detailed(f"file://{p.as_posix()}")
            self.assertEqual(result.content, b"FAKE")
            self.assertEqual(result.file_name, "call.mp3")
            self.assertIn("audio", result.content_type)

    def test_download_call_record_detailed_supports_local_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "call.wav"
            p.write_bytes(b"FAKEWAV")
            result = download_call_record_detailed(str(p))
            self.assertEqual(result.content, b"FAKEWAV")
            self.assertEqual(result.file_name, "call.wav")
            self.assertIn("audio", result.content_type)

