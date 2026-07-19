"""Migration-first Backend process entrypoint."""

import os
from pathlib import Path

from migrations.bootstrap import upgrade_backend_schema

BACKEND_DIR = Path(__file__).resolve().parent


def main() -> None:
    upgrade_backend_schema()
    os.execvp(
        "uvicorn",
        ["uvicorn", "main:app", "--app-dir", str(BACKEND_DIR), "--host", "0.0.0.0", "--port", "8000"],
    )


if __name__ == "__main__":
    main()
