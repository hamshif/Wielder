"""Utilities for configuring a Spark 4 runtime backed by Java 17+."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping

EnvView = Mapping[str, str]
EnvMutation = MutableMapping[str, str]

MIN_JAVA_MAJOR = 17
SPARK_MAJOR_FAMILY = 4
_SPARK_ENV_VARS = ("SPARK4_HOME", "SPARK_HOME", "PYSPARK_HOME")


def _java_major(java_home: Path) -> int | None:
    java_bin = java_home / "bin" / "java"
    if not java_bin.exists():
        return None
    try:
        output = subprocess.check_output(
            [str(java_bin), "-version"], stderr=subprocess.STDOUT, text=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.search(r'version\s+"(?P<ver>[0-9]+(?:\.[0-9]+)*)', output)
    if not match:
        return None
    components = match.group("ver").split(".")
    if components[0] == "1" and len(components) > 1:
        return int(components[1])
    return int(components[0])


def _candidate_java_homes(
    env: EnvView | None = None,
    additional_candidates: Iterable[Path] | None = None,
) -> list[Path]:
    env = env or os.environ
    candidates: list[Path] = []

    existing = env.get("JAVA_HOME")
    if existing:
        candidates.append(Path(existing))

    jenv_root = Path(env.get("JENV_ROOT", Path.home() / ".jenv"))
    if shutil.which("jenv"):
        try:
            version_name = subprocess.check_output(
                ["jenv", "version-name"], text=True, stderr=subprocess.DEVNULL
            ).strip()
            candidates.append(jenv_root / "versions" / version_name)
        except (OSError, subprocess.CalledProcessError):
            pass

    versions_dir = jenv_root / "versions"
    if versions_dir.exists():
        for path in sorted(versions_dir.iterdir(), reverse=True):
            candidates.append(path)

    candidates.extend(
        Path(path)
        for path in (
            "/usr/lib/jvm/java-21-openjdk-amd64",
            "/usr/lib/jvm/java-17-openjdk-amd64",
        )
    )

    java_path = shutil.which("java")
    if java_path:
        candidates.append(Path(java_path).resolve().parent.parent)

    if additional_candidates:
        candidates.extend(Path(candidate) for candidate in additional_candidates)

    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def detect_java_home(
    *,
    min_major: int = MIN_JAVA_MAJOR,
    env: EnvView | None = None,
    additional_candidates: Iterable[Path] | None = None,
) -> Path:
    """Return a Java home path whose runtime version satisfies ``min_major``."""

    for candidate in _candidate_java_homes(env, additional_candidates):
        if not (candidate / "bin" / "java").exists():
            continue
        major = _java_major(candidate)
        if major and major >= min_major:
            return candidate
    raise RuntimeError(f"Unable to determine JAVA_HOME >= {min_major}; set it explicitly.")


def _spark_release_major(spark_home: Path) -> int | None:
    release_file = spark_home / "RELEASE"
    if not release_file.exists():
        return None
    try:
        first_line = release_file.read_text().splitlines()[0]
    except OSError:
        return None
    match = re.search(r"Spark\s+(?P<version>[0-9]+(?:\.[0-9]+)*)", first_line)
    if not match:
        return None
    version = match.group("version").split(".")[0]
    try:
        return int(version)
    except ValueError:
        return None


def _has_spark_bins(path: Path) -> bool:
    spark_submit = path / "bin" / "spark-submit"
    return spark_submit.exists() and os.access(spark_submit, os.X_OK)


def _is_valid_spark4_home(path: Path, preferred_prefix: str) -> bool:
    if not path.exists():
        return False
    if not _has_spark_bins(path):
        return False
    if path.name.startswith(preferred_prefix):
        return True
    major = _spark_release_major(path)
    return bool(major and major >= SPARK_MAJOR_FAMILY)


def detect_spark_home(
    *,
    env: EnvView | None = None,
    preferred_version_prefix: str = "spark-4",
    search_roots: Iterable[Path] | None = None,
) -> Path:
    """Return the Spark 4 installation directory."""

    env = env or os.environ
    for var in _SPARK_ENV_VARS:
        candidate = env.get(var)
        if candidate and _is_valid_spark4_home(Path(candidate), preferred_version_prefix):
            return Path(candidate)

    search_dirs = list(search_roots or ())
    if not search_dirs:
        search_dirs.append(Path.home() / "opt")

    for root in search_dirs:
        if not root.exists():
            continue
        spark_dirs = sorted(
            (path for path in root.iterdir() if _is_valid_spark4_home(path, preferred_version_prefix)),
            reverse=True,
        )
        if spark_dirs:
            return spark_dirs[0]

    raise FileNotFoundError(
        "Spark 4 installation not found. Place spark-4.x under ~/opt or set SPARK_HOME/SPARK4_HOME."
    )


def bootstrap_spark_env(
    *,
    spark_home: str | Path | None = None,
    java_home: str | Path | None = None,
    pyspark_python: str | None = None,
    env: EnvMutation | None = None,
) -> tuple[Path, Path]:
    """Ensure the current environment points to Spark 4 + Java 17."""

    env_map: EnvMutation = env if env is not None else os.environ
    spark_path = Path(spark_home) if spark_home else detect_spark_home(env=env_map)
    java_path = Path(java_home) if java_home else detect_java_home(env=env_map)
    python_bin = pyspark_python or sys.executable

    if platform.system() == "Darwin":
        env_map.pop("SPARK_HOME", None)
        env_map.pop("PYSPARK_PYTHON", None)

    if not spark_path.exists():
        raise FileNotFoundError(f"Spark home not found at {spark_path}")
    if not java_path.exists():
        raise FileNotFoundError(f"Java home not found at {java_path}")

    env_map["PYSPARK_HOME"] = str(spark_path)
    env_map["SPARK_HOME"] = str(spark_path)
    env_map["JAVA_HOME"] = str(java_path)
    env_map["PYSPARK_PYTHON"] = python_bin
    env_map["PATH"] = f"{spark_path / 'bin'}:{java_path / 'bin'}:" + env_map.get("PATH", "")
    return spark_path, java_path


def set_spark_env(**kwargs) -> tuple[Path, Path]:
    """Backward-compatible alias for :func:`bootstrap_spark_env`."""

    return bootstrap_spark_env(**kwargs)


def build_spark_session(
    app_name: str,
    *,
    configs: Mapping[str, str] | None = None,
    bootstrap: bool = True,
    spark_home: str | Path | None = None,
    java_home: str | Path | None = None,
) -> "SparkSession":
    """Create or reuse a SparkSession with Wielder defaults."""

    if bootstrap:
        bootstrap_spark_env(spark_home=spark_home, java_home=java_home)

    from pyspark.sql import SparkSession

    builder = SparkSession.builder.appName(app_name)
    for key, value in (configs or {}).items():
        builder = builder.config(key, value)
    return builder.getOrCreate()


__all__ = [
    "SPARK_MAJOR_FAMILY",
    "bootstrap_spark_env",
    "build_spark_session",
    "detect_java_home",
    "detect_spark_home",
    "set_spark_env",
]
