from enum import Enum
from typing import Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator, StrictBool, StrictInt, StrictFloat

class Gate(str, Enum):
    READY = 'READY_FOR_HUMAN_REVIEW'
    HOLD = 'HOLD'
    BLOCK = 'BLOCK'

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Record(Strict):
    schema_version: Literal['1.0'] = '1.0'
    source_record_key: str = Field(min_length=1, max_length=120)
    record_version: StrictInt = Field(ge=1)
    event_time: AwareDatetime
    ingest_time: AwareDatetime
    evidence_class: Literal['SYNTHETIC','BENCHMARK','SIMULATED','OPERATIONAL','PENDING']
    trusted: StrictBool = True
    quality: Literal['GOOD','UNKNOWN','BAD'] = 'GOOD'

class Health(Record):
    domain: Literal['health']
    asset_id: str
    component_id: str
    parameter: Literal['temperature']
    value: StrictFloat = Field(allow_inf_nan=False)
    unit: Literal['C']
    urgency: StrictInt | None = Field(default=None, ge=0, le=5)
    consequence: StrictInt | None = Field(default=None, ge=0, le=5)
    warning_lead_hours: StrictFloat | None = Field(default=None, ge=0, allow_inf_nan=False)

class Technical(Record):
    domain: Literal['technical']
    asset_id: str
    component_id: str
    configuration_id: str
    alias: str
    approved: StrictBool
    valid_from: AwareDatetime
    valid_to: AwareDatetime
    @model_validator(mode='after')
    def interval(self):
        if self.valid_to <= self.valid_from:
            raise ValueError('INVALID_INTERVAL')
        return self

class Spares(Record):
    domain: Literal['spares']
    part_number: str
    compatible_components: list[str]
    quantity: StrictInt | None = Field(default=None, ge=0)
    serviceable: StrictBool | None
    lead_hours: StrictFloat | None = Field(default=None, ge=0, allow_inf_nan=False)

class Agency(Record):
    domain: Literal['agency']
    agency_id: str
    capability: StrictBool | None
    bay_capacity: StrictInt | None = Field(ge=0)
    window_start: AwareDatetime
    window_end: AwareDatetime
    approval: StrictBool | None
    @model_validator(mode='after')
    def interval(self):
        if self.window_end <= self.window_start:
            raise ValueError('INVALID_INTERVAL')
        return self

class Policy(Strict):
    version: Literal['gate-a-v1'] = 'gate-a-v1'
    rul_required: StrictBool
    max_age_hours: int = Field(default=24, ge=1, le=720)

class Bundle(Strict):
    case_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    title: str = Field(min_length=1, max_length=160)
    policy: Policy | None
    records: list[dict] = Field(min_length=1, max_length=12)

class ImportRequest(Strict):
    fixture: Literal['development-v1','holdout-v1'] | None = None
    bundles: list[Bundle] | None = Field(default=None, max_length=300)
    @model_validator(mode='after')
    def one_source(self):
        if (self.fixture is None) == (self.bundles is None):
            raise ValueError('Choose exactly one fixture or bundles source')
        return self

class Empty(Strict):
    pass

class Disposition(Strict):
    disposition: Literal['ACKNOWLEDGE_FOR_PLANNING','REJECT_RECOMMENDATION','DEFER','REQUEST_EVIDENCE']
    note: str = Field(default='', max_length=2000)

class Explanation(Strict):
    question: str = Field(default='Explain the evidence and next review steps.', min_length=1, max_length=1000)

class SuiteRequest(Strict):
    suite: Literal['frozen-v1'] = 'frozen-v1'

class Error(Strict):
    error: dict

class CaseCard(Strict):
    case_id: str
    version: int
    title: str
    asset_id: str
    component_id: str
    gate_state: Gate | None
    freshness_state: Literal['CURRENT','STALE','UNKNOWN']
    snapshot: dict
    latest_evaluation: dict | None
    rank: list

class CasePage(Strict):
    items: list[CaseCard]
    next_cursor: str | None

class RunResult(Strict):
    run_id: str
    kind: str
    status: str
    result: dict

class EvaluationResult(Strict):
    evaluation_id: str
    case_id: str
    case_version: int
    gate_state: Gate
    reason_codes: list[str]
    evidence_references: list[str]
    config_fingerprint: str
    decision_time: str
    input_snapshot: dict
    feasibility: dict
    rul: dict
