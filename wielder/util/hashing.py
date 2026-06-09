import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from pyhocon import ConfigFactory


DEFAULT_VOLATILE_CONF_KEYS = (
    "conf_evaluation_details",
    "year",
    "month",
    "day",
)


def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
    """
    Flattens a nested dictionary into a single level with dot-separated keys.
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def get_config_hash(config_subset: Dict[str, Any]) -> str:
    """
    Deterministically flattens, sorts, and hashes a configuration subset.
    Returns a short 8-character SHA-256 hex string suitable for directory nesting.
    """
    flat_config = flatten_dict(config_subset)
    # Sort keys to ensure determinism
    sorted_items = sorted(flat_config.items(), key=lambda x: x[0])
    # Convert to a stable JSON string representation
    json_repr = json.dumps(sorted_items, separators=(',', ':'))
    
    hash_object = hashlib.sha256(json_repr.encode('utf-8'))
    full_hash = hash_object.hexdigest()
    
    # Return a short UUID format purely for FS ease
    return full_hash[:8]


def _as_plain_dict(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "as_plain_ordered_dict"):
        return payload.as_plain_ordered_dict()
    if isinstance(payload, dict):
        return dict(payload)
    raise TypeError(f"Cannot hash payload of type [{type(payload).__name__}]. Expected dict-like config.")


def get_global_conf_hash(
    conf: Any,
    exclude_keys: tuple[str, ...] | list[str] = DEFAULT_VOLATILE_CONF_KEYS,
    length: int = 12,
) -> str:
    """
    Calculate a deterministic hash for a resolved configuration tree.

    `exclude_keys` are top-level volatile fields injected during runtime evaluation
    and should not influence provenance identity.
    """
    dict_state = _as_plain_dict(conf)

    for key in exclude_keys:
        dict_state.pop(key, None)

    deterministic_state = json.dumps(dict_state, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(deterministic_state.encode("utf-8")).hexdigest()[:length]


def get_local_provenance_hash(payload: dict[str, Any], length: int = 12) -> str:
    """
    Calculate a deterministic hash for a runtime payload dictionary.
    """
    deterministic_state = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(deterministic_state.encode("utf-8")).hexdigest()[:length]


def get_text_payload_hash(payload: str, length: int = 8) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def rehydrate_conf_from_uri(
    uri: str | Path,
    resolve: bool = False,
    expected_hash: str | None = None,
) -> Any:
    """
    Load a HOCON/YAML-compatible config artifact from a concrete local path.

    Provider-backed object storage should be read through a configured Bucketeer
    and then passed to :func:`rehydrate_conf_from_payload`.
    """
    conf_path = Path(uri)
    if not conf_path.exists():
        raise FileNotFoundError(f"Configuration artifact not found at [{conf_path}].")
    payload = conf_path.read_text()
    return rehydrate_conf_from_payload(payload, resolve=resolve, expected_hash=expected_hash)


def rehydrate_conf_from_payload(
    payload: str,
    resolve: bool = False,
    expected_hash: str | None = None,
) -> Any:
    if expected_hash is not None:
        actual_hash = get_text_payload_hash(payload, length=len(expected_hash))
        if actual_hash != expected_hash:
            raise ValueError(
                f"Configuration artifact hash mismatch. Expected [{expected_hash}], actual [{actual_hash}]."
            )
    return ConfigFactory.parse_string(payload, resolve=resolve)


def rehydrate_conf_from_hash(
    global_hash: str,
    provenance_config_root: str | Path,
    suffix: str = ".yaml",
    resolve: bool = False,
) -> Any:
    """
    Load a config artifact by global hash from a caller-owned provenance root.
    """
    conf_path = Path(provenance_config_root) / f"{global_hash}{suffix}"
    if not conf_path.exists():
        raise FileNotFoundError(
            f"Global configuration hash [{global_hash}] not found at [{conf_path}]."
        )
    return rehydrate_conf_from_uri(conf_path, resolve=resolve)
