from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RentalTerms:
    deposits: int | None = None
    deposit_amount: float | None = None
    advance_rents: int | None = None
    entry_total: float | None = None
    guarantor: bool | None = None
    payslips: bool | None = None
    tax_return: bool | None = None
    work_contract: bool | None = None
    other_documents: list[str] = field(default_factory=list)
    included_expenses: list[str] = field(default_factory=list)
    minimum_contract_months: int | None = None
    equipped_kitchen: bool | None = None
    pets_allowed: bool | None = None


@dataclass
class Listing:
    source: str
    source_id: str
    url: str
    title: str
    description: str = ""
    price: float | None = None
    area_m2: float | None = None
    typology: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    floor: int | None = None
    elevator: bool | None = None
    parking: bool | None = None
    fiber: bool | None = None
    quiet: bool | None = None
    natural_light: bool | None = None
    published_at: str | None = None
    first_seen_at: str | None = None
    image_url: str | None = None
    terms: RentalTerms = field(default_factory=RentalTerms)
    extracted_signals: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    peak_drive_minutes: int | None = None
    drive_estimate_kind: str | None = None
    public_transport_bonus: bool = False
    price_per_m2: float | None = None
    local_median_price_per_m2: float | None = None
    score: float = 0.0
    recommended: bool = False
    rejection_reasons: list[str] = field(default_factory=list)
    recommendation_reasons: list[str] = field(default_factory=list)
    fraud_flags: list[str] = field(default_factory=list)
    fingerprint: str | None = None
    event: str = "new"
    previous_price: float | None = None

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def full_text(self) -> str:
        return f"{self.title}\n{self.description}".strip()

    def public_record(self) -> dict[str, Any]:
        """Estado mínimo: não guarda a descrição integral do portal."""
        data = asdict(self)
        data["decision_reasons"] = (
            list(self.recommendation_reasons) if self.recommended else list(self.rejection_reasons)
        )
        data.pop("description", None)
        data.pop("missing", None)
        data.pop("recommendation_reasons", None)
        data.pop("rejection_reasons", None)
        data.pop("fraud_flags", None)
        data.pop("extracted_signals", None)
        return data
