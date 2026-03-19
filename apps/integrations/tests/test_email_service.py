import tempfile
from pathlib import Path

from django.core import mail
from django.test import SimpleTestCase, override_settings

from apps.integrations.services.email_service import send_email_with_attachment


class EmailServiceTests(SimpleTestCase):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.test",
        DOCUMENTS_EMAIL_TO="docs@example.test",
    )
    def test_send_email_with_attachment_attaches_pdf(self):
        mail.outbox = []
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "test.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test")

            sent = send_email_with_attachment(
                subject="Test",
                body="Body",
                attachment_path=pdf_path,
            )

        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["docs@example.test"])
        self.assertEqual(len(msg.attachments), 1)
        attachment_name = msg.attachments[0][0]
        self.assertTrue(str(attachment_name).endswith(".pdf"))
