from __future__ import annotations

import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
from random import Random
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


T = TypeVar("T")


class NudnikEngine(StrEnum):
    DIRECT = "direct"
    FUTURES = "futures"
    SPARK = "spark"


class NudnikTransport(StrEnum):
    DIRECT = "direct"
    OBJECT_STORE = "object_store"
    TOPIC = "topic"


class NudnikSourceMode(StrEnum):
    GENERATED = "generated"
    EXISTING_EVENTS = "existing_events"
    OBJECT_STORE = "object_store"
    TABLE = "table"


class NudnikSinkMode(StrEnum):
    VERSIONED_TEST = "versioned_test"
    CANONICAL = "canonical"


class NudnikPressureMode(StrEnum):
    DETERMINISTIC = "deterministic"
    STOCHASTIC = "stochastic"


class NudnikDuplicateMode(StrEnum):
    NONE = "none"
    SAME_EVENT = "same_event"
    SAME_ROW_KEYS = "same_row_keys"
    SOURCE_COLLISION = "source_collision"


class NudnikPressure(BaseModel):
    model_config = ConfigDict(frozen=True)

    # This is the scale knob. Unit, integration, and load tests should differ
    # mostly by pressure, transport, and sink, not by separate fake logic.
    count: int = 1
    concurrency: int = 1
    batch_interval_seconds: float = 0.0
    mode: NudnikPressureMode = NudnikPressureMode.DETERMINISTIC
    seed: int | None = None
    count_min: int | None = None
    count_max: int | None = None
    concurrency_min: int | None = None
    concurrency_max: int | None = None
    batch_interval_min_seconds: float | None = None
    batch_interval_max_seconds: float | None = None

    @field_validator("count", "concurrency")
    @classmethod
    def _positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Nudnik pressure count and concurrency must be positive.")
        return value

    @field_validator(
        "batch_interval_seconds",
        "batch_interval_min_seconds",
        "batch_interval_max_seconds",
    )
    @classmethod
    def _non_negative_interval(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("Nudnik pressure intervals must be non-negative.")
        return value

    def sample(self, *, random: Random | None = None) -> "NudnikPressure":
        if self.mode == NudnikPressureMode.DETERMINISTIC:
            return self
        rng = random or Random(self.seed)
        return self.model_copy(
            update={
                "count": _sample_int(rng, self.count_min, self.count_max, self.count),
                "concurrency": _sample_int(
                    rng,
                    self.concurrency_min,
                    self.concurrency_max,
                    self.concurrency,
                ),
                "batch_interval_seconds": _sample_float(
                    rng,
                    self.batch_interval_min_seconds,
                    self.batch_interval_max_seconds,
                    self.batch_interval_seconds,
                ),
                "mode": NudnikPressureMode.DETERMINISTIC,
            }
        )


class NudnikScenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    version: str = "v0"
    parameters: dict[str, Any] = Field(default_factory=dict)


class NudnikSink(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: NudnikSinkMode = NudnikSinkMode.VERSIONED_TEST
    root_key: str | None = None
    cleanup_before_run: bool = True
    cleanup_after_run: bool = False


class NudnikSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: NudnikSourceMode = NudnikSourceMode.GENERATED
    root_key: str | None = None
    event_keys: list[str] = Field(default_factory=list)
    table_uri: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class NudnikVariation(BaseModel):
    model_config = ConfigDict(frozen=True)

    seed: int | None = None
    duplicate_mode: NudnikDuplicateMode = NudnikDuplicateMode.NONE
    duplicate_rate: float = 0.0
    duplicate_count: int = 0
    failure_rate: float = 0.0
    jitter_fields: list[str] = Field(default_factory=list)
    collision_fields: list[str] = Field(default_factory=list)

    @field_validator("duplicate_rate", "failure_rate")
    @classmethod
    def _probability(cls, value: float) -> float:
        if value < 0.0 or value > 1.0:
            raise ValueError("Nudnik variation probabilities must be between 0 and 1.")
        return value

    @field_validator("duplicate_count")
    @classmethod
    def _non_negative_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Nudnik variation duplicate_count must be non-negative.")
        return value


class NudnikRunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    scenario: NudnikScenario
    source: NudnikSource = Field(default_factory=NudnikSource)
    pressure: NudnikPressure = Field(default_factory=NudnikPressure)
    variation: NudnikVariation = Field(default_factory=NudnikVariation)
    engine: NudnikEngine = NudnikEngine.DIRECT
    transport: NudnikTransport = NudnikTransport.DIRECT
    sink: NudnikSink = Field(default_factory=NudnikSink)

    def sampled_pressure(self) -> NudnikPressure:
        return self.pressure.sample()

    def sampled(self) -> "NudnikRunConfig":
        return self.model_copy(update={"pressure": self.sampled_pressure()})


class NudnikPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    key: str
    payload: Any
    metadata: dict[str, Any] = Field(default_factory=dict)


class NudnikReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    scenario_name: str
    scenario_version: str
    engine: NudnikEngine
    transport: NudnikTransport
    source_mode: NudnikSourceMode
    sink_mode: NudnikSinkMode
    pressure_mode: NudnikPressureMode
    duplicate_mode: NudnikDuplicateMode
    duplicate_count: int
    requested_count: int
    requested_concurrency: int
    batch_interval_seconds: float
    produced_count: int
    started_at_epoch: int
    finished_at_epoch: int
    row_counts: dict[str, int] = Field(default_factory=dict)
    artifact_uris: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class WielderNudnik(ABC, Generic[T]):
    """Base class for scenarioable Wielder tests.

    A concrete Nudnik should keep `build_one()` pure enough to pass into direct
    loops, futures, or Spark-style mapping. Side effects belong in `write_one()`
    or in a downstream app-specific sink.
    """

    def __init__(self, config: NudnikRunConfig) -> None:
        self.config = config

    @abstractmethod
    def build_one(self, index: int) -> T:
        pass

    def build_many(self) -> list[T]:
        sampled_config = self.config.sampled()
        return self._build_many_for_config(sampled_config)

    def _build_many_for_config(self, config: NudnikRunConfig) -> list[T]:
        if config.engine == NudnikEngine.FUTURES:
            return self._build_many_with_futures(config)
        if config.engine == NudnikEngine.SPARK:
            raise NotImplementedError(
                "WielderNudnik defines the Spark-capable contract, but concrete "
                "apps own Spark session/dataframe execution."
            )
        return [self.build_one(index) for index in range(config.pressure.count)]

    def write_one(self, item: T) -> None:
        del item

    def run(self) -> NudnikReport:
        sampled_config = self.config.sampled()
        started_at_epoch = int(time.time())
        items = self._build_many_for_config(sampled_config)
        if sampled_config.pressure.batch_interval_seconds > 0:
            time.sleep(sampled_config.pressure.batch_interval_seconds)
        for item in items:
            self.write_one(item)
        finished_at_epoch = int(time.time())
        return NudnikReport(
            name=sampled_config.name,
            scenario_name=sampled_config.scenario.name,
            scenario_version=sampled_config.scenario.version,
            engine=sampled_config.engine,
            transport=sampled_config.transport,
            source_mode=sampled_config.source.mode,
            sink_mode=sampled_config.sink.mode,
            pressure_mode=self.config.pressure.mode,
            duplicate_mode=sampled_config.variation.duplicate_mode,
            duplicate_count=sampled_config.variation.duplicate_count,
            requested_count=sampled_config.pressure.count,
            requested_concurrency=sampled_config.pressure.concurrency,
            batch_interval_seconds=sampled_config.pressure.batch_interval_seconds,
            produced_count=len(items),
            started_at_epoch=started_at_epoch,
            finished_at_epoch=finished_at_epoch,
        )

    def _build_many_with_futures(self, config: NudnikRunConfig) -> list[T]:
        max_workers = max(1, int(config.pressure.concurrency))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(self.build_one, range(config.pressure.count)))


def _sample_int(rng: Random, low: int | None, high: int | None, fallback: int) -> int:
    if low is None and high is None:
        return fallback
    lower = fallback if low is None else low
    upper = fallback if high is None else high
    if lower < 1 or upper < 1:
        raise ValueError("Nudnik stochastic integer pressure bounds must be positive.")
    if lower > upper:
        raise ValueError("Nudnik stochastic integer pressure lower bound exceeds upper bound.")
    return rng.randint(lower, upper)


def _sample_float(rng: Random, low: float | None, high: float | None, fallback: float) -> float:
    if low is None and high is None:
        return fallback
    lower = fallback if low is None else low
    upper = fallback if high is None else high
    if lower < 0 or upper < 0:
        raise ValueError("Nudnik stochastic interval bounds must be non-negative.")
    if lower > upper:
        raise ValueError("Nudnik stochastic interval lower bound exceeds upper bound.")
    return rng.uniform(lower, upper)
