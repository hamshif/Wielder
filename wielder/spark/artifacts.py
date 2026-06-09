from __future__ import annotations

from wielder.python.artifactor import (
    PythonArtifactBundle as PySparkArtifactBundle,
    PythonArtifactBundleSpec as PySparkArtifactBundleSpec,
    PythonArtifactSource,
    publish_python_artifact_bundle,
)


def publish_pyspark_artifact_bundle(
    spec: PySparkArtifactBundleSpec,
    *,
    bucketeer,
) -> PySparkArtifactBundle:
    return publish_python_artifact_bundle(spec, bucketeer=bucketeer)


def publish_local_pyspark_artifact_bundle(spec: PySparkArtifactBundleSpec) -> PySparkArtifactBundle:
    raise RuntimeError(
        "publish_local_pyspark_artifact_bundle has been replaced by "
        "publish_pyspark_artifact_bundle(spec, bucketeer=...). "
        "PySpark artifacts must publish through the configured Bucketeer bucket/key boundary."
    )
