from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PySparkCleanupTarget:
    bucket: str
    root_key: str
    label: str = "pyspark"
    recursive: bool = True
