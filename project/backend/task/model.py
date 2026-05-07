from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Task:
    id: str
    status: str
    progress: float
    current_row: int
    total_rows: int
    file_path: str
    output_path: str
    selected_column: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    company_name: Optional[str] = None
    address_detail: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    delivery_note: Optional[str] = None
    error: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
