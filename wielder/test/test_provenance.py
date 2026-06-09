import pytest
from pyhocon import ConfigFactory
from wielder.util.telemetry import get_telemetry
from wielder.util.hashing import (
    get_config_hash,
    flatten_dict,
    get_global_conf_hash,
    get_local_provenance_hash,
    rehydrate_conf_from_hash,
    rehydrate_conf_from_uri,
)

def test_telemetry_structure():
    telemetry = get_telemetry()
    assert "os" in telemetry
    assert "system" in telemetry["os"]
    assert "python" in telemetry
    assert "version" in telemetry["python"]
    assert "git" in telemetry
    assert "commit_hash" in telemetry["git"]
    assert "whoami" in telemetry["user"]

def test_dictionary_flattening():
    nested = {
        "level1": {
            "level2": {
                "key": "value"
            },
            "other_key": 123
        },
        "flat_key": True
    }
    
    flat = flatten_dict(nested)
    
    assert flat["level1.level2.key"] == "value"
    assert flat["level1.other_key"] == 123
    assert flat["flat_key"] is True
    assert "level1" not in flat

def test_hashing_determinism():
    dict_a = {
        "agent": {"id": "antigravity"},
        "model": {"temperature": 0.0, "type": "gpt-4o"}
    }
    
    # dict_b has identical keys/values but defined in reverse order
    dict_b = {
        "model": {"type": "gpt-4o", "temperature": 0.0},
        "agent": {"id": "antigravity"}
    }
    
    hash_a = get_config_hash(dict_a)
    hash_b = get_config_hash(dict_b)
    
    # Determinism demands these are perfectly mathematically identical
    assert hash_a == hash_b
    assert len(hash_a) == 8  # Enforce short uuid length


def test_global_conf_hash_determinism_and_volatile_exclusion():
    config_a = ConfigFactory.from_dict({
        "conf_evaluation_details": {"timestamp": "first"},
        "year": "2026",
        "month": "04",
        "nested_block": {
            "alpha": 1,
            "beta": 2,
        },
        "model_name": "model_base_default_v1.0.0",
    })
    config_b = ConfigFactory.from_dict({
        "model_name": "model_base_default_v1.0.0",
        "nested_block": {
            "beta": 2,
            "alpha": 1,
        },
        "month": "05",
        "year": "2027",
        "conf_evaluation_details": {"timestamp": "second"},
    })

    hash_a = get_global_conf_hash(config_a)
    hash_b = get_global_conf_hash(config_b)

    assert hash_a == hash_b
    assert len(hash_a) == 12


def test_local_provenance_hash_determinism():
    payload_a = {
        "domain_prime_metrics": {
            "plddt": 95.5,
            "msa_depth": 5000,
        },
        "target_id": "grpr_msa_job",
        "pointer_uris": ["s3://foo", "s3://bar"],
    }
    payload_b = {
        "pointer_uris": ["s3://foo", "s3://bar"],
        "target_id": "grpr_msa_job",
        "domain_prime_metrics": {
            "msa_depth": 5000,
            "plddt": 95.5,
        },
    }

    assert get_local_provenance_hash(payload_a) == get_local_provenance_hash(payload_b)


def test_rehydrate_conf_from_uri_and_hash(tmp_path):
    provenance_root = tmp_path / "provenance" / "configs"
    provenance_root.mkdir(parents=True)
    conf_path = provenance_root / "abc123.yaml"
    conf_path.write_text('alpha = 1\nnested.beta = "two"\n')

    conf_by_uri = rehydrate_conf_from_uri(conf_path)
    conf_by_hash = rehydrate_conf_from_hash("abc123", provenance_root)

    assert conf_by_uri.alpha == 1
    assert conf_by_uri.nested.beta == "two"
    assert conf_by_hash.alpha == 1
    assert conf_by_hash.nested.beta == "two"
