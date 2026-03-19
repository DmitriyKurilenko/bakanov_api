from ninja import Schema


class TelephonyWebhookPayload(Schema):
    call_id: str
    record_url: str
    deal_id: int | None = None


class GoogleFormWebhookPayload(Schema):
    email: str
    name: str
    source_text: str
