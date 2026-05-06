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
    name_field: Optional[str] = None
    address_field: Optional[str] = None
    phone_field: Optional[str] = None
    error: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
