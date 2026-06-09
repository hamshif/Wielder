from wielder.nudnik import (
    NudnikDuplicateMode,
    NudnikEngine,
    NudnikPressure,
    NudnikPressureMode,
    NudnikRunConfig,
    NudnikScenario,
    NudnikSource,
    NudnikSourceMode,
    NudnikVariation,
    WielderNudnik,
)


class ToyNudnik(WielderNudnik[dict]):
    def build_one(self, index: int) -> dict:
        return {
            "index": index,
            "value": index * 2,
            "scenario": self.config.scenario.name,
        }


def test_nudnik_direct_engine_reuses_single_builder():
    nudnik = ToyNudnik(
        NudnikRunConfig(
            name="ToyNudnik",
            scenario=NudnikScenario(name="toy", version="v0"),
            pressure=NudnikPressure(count=3),
            engine=NudnikEngine.DIRECT,
        )
    )

    payloads = nudnik.build_many()
    report = nudnik.run()

    assert [payload["value"] for payload in payloads] == [0, 2, 4]
    assert report.name == "ToyNudnik"
    assert report.source_mode == NudnikSourceMode.GENERATED
    assert report.duplicate_mode == NudnikDuplicateMode.NONE
    assert report.duplicate_count == 0
    assert report.requested_count == 3
    assert report.requested_concurrency == 1
    assert report.batch_interval_seconds == 0.0
    assert report.produced_count == 3


def test_nudnik_futures_engine_reuses_single_builder():
    nudnik = ToyNudnik(
        NudnikRunConfig(
            name="ToyNudnik",
            scenario=NudnikScenario(name="toy", version="v0"),
            pressure=NudnikPressure(count=5, concurrency=2),
            engine=NudnikEngine.FUTURES,
        )
    )

    payloads = nudnik.build_many()

    assert [payload["index"] for payload in payloads] == [0, 1, 2, 3, 4]


def test_nudnik_stochastic_pressure_is_reproducible():
    config = NudnikRunConfig(
        name="ToyNudnik",
        scenario=NudnikScenario(name="toy", version="v0"),
        source=NudnikSource(
            mode=NudnikSourceMode.EXISTING_EVENTS,
            event_keys=["events/toy/0.json", "events/toy/1.json"],
        ),
        pressure=NudnikPressure(
            mode=NudnikPressureMode.STOCHASTIC,
            seed=17,
            count_min=3,
            count_max=7,
            concurrency_min=1,
            concurrency_max=4,
            batch_interval_min_seconds=0.0,
            batch_interval_max_seconds=0.0,
        ),
        variation=NudnikVariation(
            duplicate_mode=NudnikDuplicateMode.SAME_ROW_KEYS,
            duplicate_count=2,
            duplicate_rate=0.5,
            collision_fields=["key"],
        ),
        engine=NudnikEngine.FUTURES,
    )

    first_sample = config.sampled_pressure()
    second_sample = config.sampled_pressure()
    nudnik = ToyNudnik(config)
    report = nudnik.run()

    assert first_sample == second_sample
    assert 3 <= report.requested_count <= 7
    assert 1 <= report.requested_concurrency <= 4
    assert report.source_mode == NudnikSourceMode.EXISTING_EVENTS
    assert report.pressure_mode == NudnikPressureMode.STOCHASTIC
    assert report.duplicate_mode == NudnikDuplicateMode.SAME_ROW_KEYS
    assert report.duplicate_count == 2
    assert report.produced_count == report.requested_count
