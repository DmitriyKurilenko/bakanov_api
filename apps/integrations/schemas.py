from ninja import Schema


class TelephonyWebhookPayload(Schema):
    call_id: str
    record_url: str
    deal_id: int | None = None


class GoogleFormWebhookPayload(Schema):
    email: str
    name: str
    source_text: str


# ------------------------------------------------------------------
# Bitrix24
# ------------------------------------------------------------------

class Bitrix24WebhookResponse(Schema):
    event: str
    entity_id: int | None = None
    status: str
    detail: str = ""


class Bitrix24EntityResponse(Schema):
    status: str
    entity_type: str
    entity_id: int
    data: dict
