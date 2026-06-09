import os
import shutil
import sys
import platform
import subprocess
import re
from pathlib import Path
from typing import Mapping, MutableMapping, Iterable
from contextlib import contextmanager

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

def _apply_spark_env_mutations(
    *,
    spark_home: str | Path | None = None,
    java_home: str | Path | None = None,
    pyspark_python: str | None = None,
) -> None:
    """Mutates the active os.environ with Spark and Java paths."""
    if (
        spark_home is None
        and java_home is None
        and pyspark_python is None
        and _already_in_spark_submit_driver(os.environ)
    ):
        return

    spark_path = Path(spark_home) if spark_home else detect_spark_home()
    java_path = Path(java_home) if java_home else detect_java_home()
    python_bin = pyspark_python or sys.executable

    if platform.system() == "Darwin":
        os.environ.pop("SPARK_HOME", None)
        os.environ.pop("PYSPARK_PYTHON", None)

    if not spark_path.exists():
        raise FileNotFoundError(f"Spark home not found at {spark_path}")
    if not java_path.exists():
        raise FileNotFoundError(f"Java home not found at {java_path}")

    os.environ["PYSPARK_HOME"] = str(spark_path)
    os.environ["SPARK_HOME"] = str(spark_path)
    os.environ["JAVA_HOME"] = str(java_path)
    os.environ["PYSPARK_PYTHON"] = python_bin
    os.environ["PATH"] = f"{spark_path / 'bin'}:{java_path / 'bin'}:" + os.environ.get("PATH", "")


def _already_in_spark_submit_driver(env: EnvView) -> bool:
    return bool(
        env.get("SPARK_YARN_STAGING_DIR")
        or (
            env.get("CONTAINER_ID")
            and env.get("SPARK_USER")
            and "pyspark" in env.get("PYTHONPATH", "")
        )
    )


@contextmanager
def scoped_spark_env(
    *,
    spark_home: str | Path | None = None,
    java_home: str | Path | None = None,
    pyspark_python: str | None = None,
):
    """
    Context manager that safely initializes the PySpark environment (JAVA_HOME, SPARK_HOME)
    without polluting the global application state. State is restored upon exiting the manager.
    
    Usage:
        with scoped_spark_env():
            spark = SparkSession.builder.getOrCreate()
    """
    original_env = dict(os.environ)
    try:
        _apply_spark_env_mutations(
            spark_home=spark_home, 
            java_home=java_home, 
            pyspark_python=pyspark_python
        )
        yield
    finally:
        os.environ.clear()
        os.environ.update(original_env)
