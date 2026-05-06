from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from task.model import Task
from storage.db import get_conn


class TaskManager:
    """Task persistence and state transitions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_task(self, task: Task) -> None:
        with self._lock:
            conn = get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO tasks (
                        id, status, progress, current_row, total_rows,
                        file_path, output_path, selected_column,
                        name_field, address_field, phone_field, error,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.id,
                        task.status,
                        task.progress,
                        task.current_row,
                        task.total_rows,
                        task.file_path,
                        task.output_path,
                        task.selected_column,
                        task.name_field,
                        task.address_field,
                        task.phone_field,
                        task.error,
                        task.created_at or self._now(),
                        task.updated_at or self._now(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_task(self, task_id: str) -> Optional[Task]:
        conn = get_conn()
        try:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return None
            return Task(**dict(row))
        finally:
            conn.close()

    def update_task(self, task_id: str, **kwargs) -> Optional[Task]:
        with self._lock:
            task = self.get_task(task_id)
            if not task:
                return None
            allowed = set(task.to_dict().keys()) - {"id", "created_at"}
            fields = []
            values = []
            for key, value in kwargs.items():
                if key in allowed:
                    fields.append(f"{key} = ?")
                    values.append(value)
            fields.append("updated_at = ?")
            values.append(self._now())
            values.append(task_id)
            conn = get_conn()
            try:
                conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", values)
                conn.commit()
            finally:
                conn.close()
            return self.get_task(task_id)
