from __future__ import annotations

from typing import Any, Dict


def load_resume(path: str) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "PyYAML is required to load resume YAML. Install with `uv add pyyaml`."
        ) from e

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError("Resume YAML must be a mapping at the top level.")
        return data

