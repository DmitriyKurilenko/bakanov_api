from ninja import Schema


class LeadRequest(Schema):
    lead_id: int


class ContractResponse(Schema):
    status: str
    contract_file_url: str | None = None
    detail: str | None = None
    warnings: list[str] | None = None


class ExtraContractResponse(Schema):
    status: str
    extra_contract_file_url: str | None = None
    detail: str | None = None
    warnings: list[str] | None = None


class AssignmentResponse(Schema):
    status: str
    responsible_user_id: int


class GenericResponse(Schema):
    status: str
    detail: str
