from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuração não encontrada: {config_path}. "
            "Copie config.example.yml para config.yml."
        )
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    required = ["search", "geo", "sources", "telegram"]
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"Faltam secções na configuração: {', '.join(missing)}")
    return config

