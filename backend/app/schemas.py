from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


def validate_barcode(value: str) -> str:
    if not value.isascii() or not value.isdigit() or len(value) not in {8, 12, 13, 14}:
        raise ValueError('Barcode must be a GTIN with 8, 12, 13 or 14 ASCII digits.')
    total = sum(int(digit) * (3 if i % 2 == 0 else 1) for i, digit in enumerate(reversed(value[:-1])))
    if (10 - total % 10) % 10 != int(value[-1]):
        raise ValueError('Barcode checksum is invalid.')
    return value


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['recall', 'certification', 'warning']
    title: str = Field(min_length=1, max_length=1000)
    source_url: HttpUrl
    checked_at: datetime
    jurisdiction: str = Field(min_length=1, max_length=100)
    scope: str = Field(min_length=1, max_length=1000, description='Applicable model, batch or serial range')


class ProductRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    name: str = Field(min_length=1, max_length=300)
    brand: str = Field(default='', max_length=200)
    category: str = Field(default='', max_length=200)
    barcode: str | None = None
    batch_number: str | None = Field(default=None, max_length=100)
    description: str = Field(default='', max_length=2000)
    source_url: HttpUrl
    checked_at: datetime
    evidence: list[EvidenceRecord] = Field(default_factory=list, max_length=100)
    alternatives: list[str] = Field(default_factory=list, max_length=30)

    @field_validator('barcode')
    @classmethod
    def valid_barcode(cls, value):
        return validate_barcode(value) if value is not None else value


class ImageRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    upload_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class VerifyRequest(ImageRequest):
    barcode: str | None = None
    algorithm: Literal['exact', 'lsh'] = 'exact'

    @field_validator('barcode')
    @classmethod
    def valid_barcode(cls, value):
        return validate_barcode(value) if value is not None else value
