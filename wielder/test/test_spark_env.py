import os

from wielder.util.spark_env import scoped_spark_env


def test_scoped_spark_env_respects_existing_yarn_driver_env(monkeypatch):
    monkeypatch.delenv("SPARK_HOME", raising=False)
    monkeypatch.setenv("SPARK_YARN_STAGING_DIR", "hdfs://cluster/user/hadoop/.sparkStaging/app")
    monkeypatch.setenv("JAVA_HOME", "/usr/lib/jvm/jre-17")
    monkeypatch.setenv("PYSPARK_PYTHON", "/usr/bin/python3.11")

    with scoped_spark_env():
        assert "SPARK_HOME" not in os.environ
        assert os.environ["PYSPARK_PYTHON"] == "/usr/bin/python3.11"
