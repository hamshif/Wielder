from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable

from wielder.spark.types import PySparkCleanupTarget


@dataclass(frozen=True)
class PythonArtifactSource:
    name: str
    source: str
    artifact_name: str
    artifact_kind: str = "file"


@dataclass(frozen=True)
class PythonArchiveSource:
    name: str
    source: str
    artifact_name: str
    alias: str
    artifact_kind: str = "file"


@dataclass(frozen=True)
class PythonArtifactBundleSpec:
    job_name: str
    version: str
    bucket: str
    root_key: str
    entrypoint: str
    entrypoint_artifact_name: str
    py_file_sources: list[PythonArtifactSource] = field(default_factory=list)
    manifest_name: str = "manifest.json"


@dataclass(frozen=True)
class PythonArtifactBundle:
    job_name: str
    version: str
    bucket: str
    root_key: str
    root_uri: str
    entrypoint_key: str
    entrypoint_uri: str
    py_file_keys: list[str]
    py_files: list[str]
    manifest_key: str
    manifest_uri: str
    manifest: dict


@dataclass(frozen=True)
class WieldedPythonArtifacts:
    conf_publication: dict[str, str]
    entrypoint: str
    py_files: list[str]
    archives: list[str]
    manifest_uri: str
    cleanup_targets: list[PySparkCleanupTarget]


ResolvedConfPublisher = Callable[..., dict[str, str]]


def prepare_wielded_python_artifacts(
    *,
    target_conf: Any,
    app_name: str,
    repo_root: Path,
    runtime_conf: Any,
    job_conf: Any,
    bootstrap_ref_path: tuple[str, ...] = (),
    unique_name: str,
    write: bool,
    bucketeer: Any,
    force_write: bool = False,
    publish_resolved_conf: ResolvedConfPublisher | None = None,
    archive_sources: list[PythonArchiveSource] | None = None,
) -> WieldedPythonArtifacts:
    conf_publication = {}
    if publish_resolved_conf is not None:
        if not bootstrap_ref_path:
            raise ValueError("bootstrap_ref_path is required when publish_resolved_conf is configured.")
        conf_publication = publish_resolved_conf(
            target_conf=target_conf,
            app_name=app_name,
            bucket=str(runtime_conf.resolved_conf.bucket),
            bootstrap_ref_path=bootstrap_ref_path,
            unique_name=unique_name,
            write=write,
        )
    artifact_version = _artifact_version(runtime_conf, target_conf, unique_name)
    py_file_sources = python_artifact_sources_from_conf(job_conf, repo_root)
    configured_archive_sources = python_archive_sources_from_conf(job_conf, repo_root)
    effective_archive_sources = [
        *configured_archive_sources,
        *(archive_sources or []),
    ]
    bundle_spec = PythonArtifactBundleSpec(
        job_name=str(job_conf.name),
        version=artifact_version,
        bucket=str(runtime_conf.artifacts.bucket),
        root_key=str(runtime_conf.artifacts.root_key),
        entrypoint=(repo_root / str(job_conf.entrypoint)).as_posix(),
        entrypoint_artifact_name=str(job_conf.entrypoint_artifact_name),
        py_file_sources=py_file_sources,
    )
    bundle_root_key = python_artifact_bundle_root_key(bundle_spec)
    if write:
        missing_keys = []
        if not force_write:
            missing_keys = missing_python_artifact_set_keys(
                bundle_spec,
                bucketeer=bucketeer,
                archive_sources=effective_archive_sources,
            )

        if force_write or missing_keys:
            if missing_keys:
                logging.info(
                    "Publishing PySpark artifacts for [%s:%s]; missing [%d] object(s).",
                    bundle_spec.job_name,
                    bundle_spec.version,
                    len(missing_keys),
                )
            elif force_write:
                logging.info(
                    "Publishing PySpark artifacts for [%s:%s]; force_write is enabled.",
                    bundle_spec.job_name,
                    bundle_spec.version,
                )
            bundle = publish_python_artifact_bundle(bundle_spec, bucketeer=bucketeer)
            entrypoint = bundle.entrypoint_uri
            py_files = bundle.py_files
            archives = publish_python_archive_sources(
                effective_archive_sources,
                bucketeer=bucketeer,
                bucket=str(runtime_conf.artifacts.bucket),
                bundle_root_key=bundle_root_key,
            )
            manifest_uri = bundle.manifest_uri
        else:
            logging.info(
                "Reusing existing PySpark artifact set for [%s:%s].",
                bundle_spec.job_name,
                bundle_spec.version,
            )
            bundle = resolve_python_artifact_bundle(bundle_spec, bucketeer=bucketeer)
            entrypoint = bundle.entrypoint_uri
            py_files = bundle.py_files
            archives = resolve_python_archive_sources(
                effective_archive_sources,
                bucketeer=bucketeer,
                bucket=str(runtime_conf.artifacts.bucket),
                bundle_root_key=bundle_root_key,
            )
            manifest_uri = bundle.manifest_uri
    else:
        entrypoint = (repo_root / str(job_conf.entrypoint)).as_posix()
        py_files = [str(item) for item in job_conf.py_files]
        archives = [str(item) for item in job_conf.archives]
        manifest_uri = "<not-published>"

    return WieldedPythonArtifacts(
        conf_publication=conf_publication,
        entrypoint=entrypoint,
        py_files=py_files,
        archives=archives,
        manifest_uri=manifest_uri,
        cleanup_targets=[
            PySparkCleanupTarget(
                bucket=str(runtime_conf.artifacts.bucket),
                root_key=bucketeer.join_object_key(
                    str(runtime_conf.artifacts.root_key),
                    str(job_conf.name),
                    artifact_version,
                ),
                label=str(job_conf.name),
            )
        ],
    )


def bootstrap_conf_app_args(artifacts: WieldedPythonArtifacts) -> list[str]:
    if "bootstrap_staged_file" not in artifacts.conf_publication:
        raise ValueError("No bootstrap config artifact was published for this PySpark job.")
    bootstrap_arg = artifacts.conf_publication.get(
        "bootstrap_staged_name",
        artifacts.conf_publication["bootstrap_staged_file"],
    )
    return [
        "--bootstrap-conf-file",
        bootstrap_arg,
    ]


def bootstrap_conf_files(artifacts: WieldedPythonArtifacts, job_conf: Any) -> list[str]:
    if "bootstrap_staged_file" not in artifacts.conf_publication:
        raise ValueError("No bootstrap config artifact was published for this PySpark job.")
    bootstrap_file = artifacts.conf_publication.get(
        "bootstrap_file_ref",
        artifacts.conf_publication["bootstrap_staged_file"],
    )
    return [
        bootstrap_file,
        *[str(item) for item in job_conf.files],
    ]


def print_wielded_python_artifact_report(
    artifacts: WieldedPythonArtifacts,
    *,
    spark_command: str | None = None,
) -> None:
    if artifacts.conf_publication:
        print(f"resolved_conf_bucket = {artifacts.conf_publication['bucket']}")
        print(f"resolved_conf_key = {artifacts.conf_publication['versioned_key']}")
        print(f"bootstrap_conf_staged_file = {artifacts.conf_publication['bootstrap_staged_file']}")
        if artifacts.conf_publication.get("bootstrap_file_ref"):
            print(f"bootstrap_conf_file_ref = {artifacts.conf_publication['bootstrap_file_ref']}")
        print(f"resolved_conf_hash = {artifacts.conf_publication['conf_hash']}")
    print(f"artifact_manifest_uri = {artifacts.manifest_uri}")
    for archive in artifacts.archives:
        print(f"archive = {archive}")
    if spark_command is not None:
        print(f"spark_command = {spark_command}")


def print_pyspark_cleanup_report(cleanup_results) -> None:
    for result in cleanup_results:
        print(
            f"deleted_artifact_target = {result.target.bucket}/{result.target.root_key} "
            f"matched={len(result.matched_keys)}"
        )


def python_artifact_sources_from_conf(job_conf: Any, repo_root: Path) -> list[PythonArtifactSource]:
    sources = []
    for source_conf in _plain_config_value(job_conf.py_file_sources):
        source_path = repo_root / str(source_conf["source"])
        sources.append(
            PythonArtifactSource(
                name=str(source_conf["name"]),
                source=source_path.as_posix(),
                artifact_name=str(source_conf["artifact_name"]),
                artifact_kind=str(source_conf["artifact_kind"]),
            )
        )
    return sources


def python_archive_sources_from_conf(job_conf: Any, repo_root: Path) -> list[PythonArchiveSource]:
    sources = []
    for source_conf in _plain_config_value(_optional_conf_value(job_conf, "archive_sources", [])):
        source_path = repo_root / str(source_conf["source"])
        sources.append(
            PythonArchiveSource(
                name=str(source_conf["name"]),
                source=source_path.as_posix(),
                artifact_name=str(source_conf["artifact_name"]),
                alias=str(source_conf["alias"]),
                artifact_kind=str(source_conf.get("artifact_kind", "zip")),
            )
        )
    return sources


def key_join(*parts: str) -> str:
    head = parts[0].strip("/")
    tail = [part.strip("/") for part in parts[1:]]
    return "/".join([head, *tail])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish_python_artifact_bundle(
    spec: PythonArtifactBundleSpec,
    *,
    bucketeer: Any,
) -> PythonArtifactBundle:
    bundle_root_key = python_artifact_bundle_root_key(spec)
    bundle_root_uri = str(bucketeer.object_uri_by_key(spec.bucket, bundle_root_key))
    entrypoint_key = python_artifact_entrypoint_key(spec)
    entrypoint_path = Path(spec.entrypoint).resolve()
    entrypoint_uri = _publish_file(bucketeer, entrypoint_path, spec.bucket, entrypoint_key)

    artifact_records = [
        {
            "role": "entrypoint",
            "name": spec.entrypoint_artifact_name,
            "bucket": spec.bucket,
            "key": entrypoint_key,
            "uri": entrypoint_uri,
            "sha256": sha256_file(entrypoint_path),
        }
    ]
    py_file_keys: list[str] = []
    py_file_uris: list[str] = []
    with TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        for source in spec.py_file_sources:
            materialized = _materialize_source(source, tmp_root)
            artifact_key = python_artifact_source_key(spec, source)
            artifact_uri = _publish_file(bucketeer, materialized, spec.bucket, artifact_key)
            py_file_keys.append(artifact_key)
            py_file_uris.append(artifact_uri)
            artifact_records.append(
                {
                    "role": "py_file",
                    "name": source.name,
                    "bucket": spec.bucket,
                    "key": artifact_key,
                    "uri": artifact_uri,
                    "sha256": sha256_file(materialized),
                }
            )

    manifest = {
        "job_name": spec.job_name,
        "version": spec.version,
        "bucket": spec.bucket,
        "root_key": bundle_root_key,
        "root_uri": bundle_root_uri,
        "entrypoint_key": entrypoint_key,
        "entrypoint_uri": entrypoint_uri,
        "py_file_keys": py_file_keys,
        "py_files": py_file_uris,
        "artifacts": artifact_records,
    }
    manifest_key = python_artifact_manifest_key(spec)
    bucketeer.upload_string(json.dumps(manifest, indent=2, sort_keys=True), spec.bucket, manifest_key)
    manifest_uri = str(bucketeer.object_uri_by_key(spec.bucket, manifest_key))

    return PythonArtifactBundle(
        job_name=spec.job_name,
        version=spec.version,
        bucket=spec.bucket,
        root_key=bundle_root_key,
        root_uri=bundle_root_uri,
        entrypoint_key=entrypoint_key,
        entrypoint_uri=entrypoint_uri,
        py_file_keys=py_file_keys,
        py_files=py_file_uris,
        manifest_key=manifest_key,
        manifest_uri=manifest_uri,
        manifest=manifest,
    )


def resolve_python_artifact_bundle(
    spec: PythonArtifactBundleSpec,
    *,
    bucketeer: Any,
) -> PythonArtifactBundle:
    bundle_root_key = python_artifact_bundle_root_key(spec)
    bundle_root_uri = str(bucketeer.object_uri_by_key(spec.bucket, bundle_root_key))
    entrypoint_key = python_artifact_entrypoint_key(spec)
    entrypoint_uri = str(bucketeer.object_uri_by_key(spec.bucket, entrypoint_key))
    py_file_keys = [
        python_artifact_source_key(spec, source)
        for source in spec.py_file_sources
    ]
    py_files = [
        str(bucketeer.object_uri_by_key(spec.bucket, key))
        for key in py_file_keys
    ]
    manifest_key = python_artifact_manifest_key(spec)
    manifest_uri = str(bucketeer.object_uri_by_key(spec.bucket, manifest_key))
    return PythonArtifactBundle(
        job_name=spec.job_name,
        version=spec.version,
        bucket=spec.bucket,
        root_key=bundle_root_key,
        root_uri=bundle_root_uri,
        entrypoint_key=entrypoint_key,
        entrypoint_uri=entrypoint_uri,
        py_file_keys=py_file_keys,
        py_files=py_files,
        manifest_key=manifest_key,
        manifest_uri=manifest_uri,
        manifest={
            "job_name": spec.job_name,
            "version": spec.version,
            "bucket": spec.bucket,
            "root_key": bundle_root_key,
            "root_uri": bundle_root_uri,
            "entrypoint_key": entrypoint_key,
            "entrypoint_uri": entrypoint_uri,
            "py_file_keys": py_file_keys,
            "py_files": py_files,
            "manifest_key": manifest_key,
            "manifest_uri": manifest_uri,
        },
    )


def publish_python_archive_sources(
    sources: list[PythonArchiveSource],
    *,
    bucketeer: Any,
    bucket: str,
    bundle_root_key: str,
) -> list[str]:
    archives: list[str] = []
    for source in sources:
        with TemporaryDirectory() as tmp_dir:
            source_path = _materialize_archive_source(source, Path(tmp_dir))
            archive_key = python_archive_source_key(source, bundle_root_key)
            archive_uri = _publish_file(bucketeer, source_path, bucket, archive_key)
            archives.append(f"{archive_uri}#{source.alias}")
    return archives


def resolve_python_archive_sources(
    sources: list[PythonArchiveSource],
    *,
    bucketeer: Any,
    bucket: str,
    bundle_root_key: str,
) -> list[str]:
    return [
        f"{bucketeer.object_uri_by_key(bucket, python_archive_source_key(source, bundle_root_key))}#{source.alias}"
        for source in sources
    ]


def python_artifact_bundle_root_key(spec: PythonArtifactBundleSpec) -> str:
    return key_join(spec.root_key, spec.job_name, spec.version)


def python_artifact_entrypoint_key(spec: PythonArtifactBundleSpec) -> str:
    return key_join(python_artifact_bundle_root_key(spec), spec.entrypoint_artifact_name)


def python_artifact_source_key(spec: PythonArtifactBundleSpec, source: PythonArtifactSource) -> str:
    return key_join(python_artifact_bundle_root_key(spec), source.artifact_name)


def python_artifact_manifest_key(spec: PythonArtifactBundleSpec) -> str:
    return key_join(python_artifact_bundle_root_key(spec), spec.manifest_name)


def python_archive_source_key(source: PythonArchiveSource, bundle_root_key: str) -> str:
    return key_join(bundle_root_key, "archives", source.artifact_name)


def python_artifact_set_keys(
    spec: PythonArtifactBundleSpec,
    *,
    archive_sources: list[PythonArchiveSource] | None = None,
) -> list[str]:
    bundle_root_key = python_artifact_bundle_root_key(spec)
    return [
        python_artifact_entrypoint_key(spec),
        *[
            python_artifact_source_key(spec, source)
            for source in spec.py_file_sources
        ],
        *[
            python_archive_source_key(source, bundle_root_key)
            for source in (archive_sources or [])
        ],
        python_artifact_manifest_key(spec),
    ]


def missing_python_artifact_set_keys(
    spec: PythonArtifactBundleSpec,
    *,
    bucketeer: Any,
    archive_sources: list[PythonArchiveSource] | None = None,
) -> list[str]:
    return [
        key
        for key in python_artifact_set_keys(spec, archive_sources=archive_sources)
        if not bucketeer.object_exists_by_key(spec.bucket, key)
    ]


def _publish_file(bucketeer: Any, source: Path, bucket: str, key: str) -> str:
    bucketeer.upload_file(source.as_posix(), bucket, key)
    return str(bucketeer.object_uri_by_key(bucket, key))


def _materialize_source(source: PythonArtifactSource, tmp_root: Path) -> Path:
    source_path = Path(source.source).resolve()
    if source.artifact_kind == "file":
        if not source_path.is_file():
            raise FileNotFoundError(f"Python artifact source file not found: {source_path}")
        return source_path
    if source.artifact_kind == "zip":
        if not source_path.is_dir():
            raise FileNotFoundError(f"Python artifact source directory not found: {source_path}")
        archive_base = tmp_root / source.artifact_name.removesuffix(".zip")
        return Path(
            shutil.make_archive(
                str(archive_base),
                "zip",
                root_dir=source_path.parent,
                base_dir=source_path.name,
            )
        )
    raise ValueError(f"Unsupported Python artifact kind [{source.artifact_kind}].")


def _materialize_archive_source(source: PythonArchiveSource, tmp_root: Path) -> Path:
    source_path = Path(source.source).resolve()
    if source.artifact_kind == "file":
        if not source_path.is_file():
            raise FileNotFoundError(f"Python archive source file not found: {source_path}")
        return source_path
    if source.artifact_kind == "zip":
        if not source_path.is_dir():
            raise FileNotFoundError(f"Python archive source directory not found: {source_path}")
        archive_base = tmp_root / source.artifact_name.removesuffix(".zip")
        return Path(
            shutil.make_archive(
                str(archive_base),
                "zip",
                root_dir=source_path.parent,
                base_dir=source_path.name,
            )
        )
    raise ValueError(f"Unsupported Python archive kind [{source.artifact_kind}].")


def _artifact_version(runtime_conf: Any, target_conf: Any, unique_name: str) -> str:
    version = str(runtime_conf.artifacts.version)
    if version == "local":
        version = f"{unique_name}--{_short_commit(target_conf)}"
    return version


def _short_commit(conf: Any) -> str:
    try:
        return str(conf.git.commit)[:8]
    except Exception:
        return "local"


def _plain_config_value(value: Any) -> Any:
    if hasattr(value, "as_plain_ordered_dict"):
        return value.as_plain_ordered_dict()
    if isinstance(value, list):
        return [_plain_config_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain_config_value(item) for key, item in value.items()}
    return value


def _optional_conf_value(conf: Any, key: str, default: Any = None) -> Any:
    if hasattr(conf, key):
        return getattr(conf, key)
    if isinstance(conf, dict):
        return conf.get(key, default)
    try:
        if key in conf:
            return conf[key]
    except TypeError:
        pass
    return default
