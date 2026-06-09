import logging
import os
from enum import Enum
from pathlib import Path
from pyhocon import ConfigFactory, ConfigTree
from typing import Any, cast

from wielder.util.arguer import get_ecosystem_parser, parse_bool_arg, parse_known_args_strict
from wielder.util.wgit import WGit
from wielder.util.util import get_whoami
import wielder.util.util as wu

logger = logging.getLogger(__name__)
TypedConfig = Any
STATIC_RUNTIME_GIT_COMMIT = "0000000000000000000000000000000000000000"
STATIC_RUNTIME_GIT_BRANCH = "runtime-artifact"


def resolve_ecosystem_conf_path(
    ecosystem_root: Path,
    ecosystem: str,
    filename: str,
    required: bool = False,
) -> Path | None:
    """
    Resolve an ecosystem-scoped config while keeping the semantic ecosystem id flat.

    Supported layouts:
      - <root>/<ecosystem>/<filename>
      - <root>/<namespace>/<ecosystem>/<filename>

    Resolution is fail-closed on ambiguity.
    """
    candidates: dict[str, Path] = {}
    for manifest_path in ecosystem_root.rglob(filename):
        if manifest_path.parent.name != ecosystem:
            continue
        candidates[manifest_path.resolve().as_posix()] = manifest_path

    resolved_candidates = sorted(candidates.values(), key=lambda p: p.resolve().as_posix())

    if not resolved_candidates:
        if required:
            raise FileNotFoundError(
                f"Could not resolve ecosystem config [{filename}] for [{ecosystem}] under [{ecosystem_root}]."
            )
        return None

    if len(resolved_candidates) > 1:
        pretty_paths = "\n".join(f"  - {path}" for path in resolved_candidates)
        raise RuntimeError(
            f"Ambiguous ecosystem config resolution for [{ecosystem}] under [{ecosystem_root}].\n"
            f"Expected exactly one match, found [{len(resolved_candidates)}]:\n{pretty_paths}"
        )

    return resolved_candidates[0]


def resolve_ecosystem_manifest_path(ecosystem_root: Path, ecosystem: str, required: bool = False) -> Path | None:
    return resolve_ecosystem_conf_path(
        ecosystem_root=ecosystem_root,
        ecosystem=ecosystem,
        filename="ecosystem_manifest.conf",
        required=required,
    )


def resolve_app_conf_path(apps_root: Path, app_name: str, required: bool = False) -> Path | None:
    """
    Resolve an app configuration by canonical relative app identity.

    Supported layouts:
      - conf/apps/<app_name>/app.conf
      - conf/apps/<namespace>/<domain>/<app_name>/app.conf

    Nested app identities must be passed with POSIX separators, for example
    "ingestion/provider/assay". Resolution is intentionally direct rather than fuzzy
    so app identity, filesystem layout, and config ownership stay aligned.
    """
    if not app_name:
        raise ValueError("App name must be non-empty.")

    if "\\" in app_name:
        raise ValueError(
            f"Invalid app name [{app_name}]. Use POSIX '/' separators for nested app identities."
        )

    if app_name != app_name.strip("/") or "//" in app_name:
        raise ValueError(f"Invalid app name [{app_name}]. App identity must be a normalized relative path.")

    if Path(app_name).is_absolute():
        raise ValueError(f"Invalid app name [{app_name}]. App identity must be relative.")

    parts = tuple(app_name.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Invalid app name [{app_name}]. App identity contains an unsafe path segment.")

    app_conf_path = apps_root.joinpath(*parts) / "app.conf"
    if app_conf_path.exists():
        return app_conf_path

    if required:
        raise FileNotFoundError(
            f"Could not resolve app config for [{app_name}] at [{app_conf_path}]. "
            "Use a canonical relative app identity such as [ingestion/provider/assay]."
        )

    return None


def log_wielder_modes(conf: ConfigTree, scope: str, mute: bool = False) -> None:
    if mute:
        return

    logger.info(
        f"\n\nStarting {scope}.\n"
        f"  wield with action [{conf.action}]\n"
        f"  Wielder modes are:\n"
        f"    - ecosystem: [{conf.ecosystem}]\n"
        f"    - stage_tier: [{conf.stage_tier}]\n"
        f"    - security: [{conf.security}]\n"
        f"    - canary: [{conf.canary}]\n"
        f"    - destroy: [{conf.destroy}]\n"
        f"    - test: [{conf.test}]\n"
    )

def _parse_hocon(path: Path) -> ConfigTree:
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"HOCON config not found at {resolved}")
    conf = ConfigFactory.parse_file(resolved.as_posix(), resolve=False)
    return cast(TypedConfig, conf)


def _is_enabled_mode(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(parse_bool_arg(value))


def normalize_cli_overrides(cli_overrides: dict | None = None) -> dict[str, Any]:
    if not cli_overrides:
        return {}

    normalized = {
        k: v.value if isinstance(v, Enum) else v
        for k, v in cli_overrides.items()
        if v is not None
    }
    if "wield" in normalized:
        normalized["action"] = normalized.pop("wield")
    if "deletion" in normalized:
        normalized["destroy"] = normalized.pop("deletion")
    return normalized


def build_cli_overrides(**overrides: Any) -> dict[str, Any]:
    return normalize_cli_overrides(overrides)


def build_cli_overrides_from_conf(conf: ConfigTree, action: Any | None = None) -> dict[str, Any]:
    """Carry the resolved Wielder mode envelope into a child app config load."""
    return build_cli_overrides(
        ecosystem=conf.ecosystem,
        stage_tier=conf.stage_tier,
        security=conf.security,
        destroy=conf.destroy,
        canary=conf.canary,
        context_conf=conf.context_conf,
        test=conf.test,
        action=conf.action if action is None else action,
    )


def _git_snapshot_injection(super_repo_root: Path) -> dict[str, Any]:
    skip_git_snapshot = os.environ.get("WIELDER_SKIP_GIT_SNAPSHOT")
    if skip_git_snapshot is not None and parse_bool_arg(skip_git_snapshot):
        return {
            "git": {
                "repo_path": super_repo_root.as_posix(),
                "local_system": "unix" if os.name != "nt" else "win",
                "awk_command": "awk",
                "commit": os.environ.get("WIELDER_GIT_COMMIT", STATIC_RUNTIME_GIT_COMMIT),
                "branch": os.environ.get("WIELDER_GIT_BRANCH", STATIC_RUNTIME_GIT_BRANCH),
                "subs": {},
                "branches": {},
            }
        }
    return WGit(super_repo_root.as_posix()).as_dict_injection()


def get_wield_project_conf(
    project_root: str,
    conf_root: str,
    project_name: str = "culture",
    runtime_defaults: dict = None,
    cli_overrides: dict | None = None,
    resolve: bool = True,
) -> TypedConfig:
    """
    Core Wielder Project Configuration Loader.
    Follows the strict multi-layer merge strategy from AGENTS.md.
    """
    context_overlays = ConfigFactory.from_dict(runtime_defaults if runtime_defaults else {})
    project_root_path = Path(project_root)
    conf_root_path = Path(conf_root)
    context_conf_name = cast(
        str,
        (runtime_defaults or {}).get("context_conf", "default_conf"),
    )
    
    # 1. Determine staging root and system identity
    stage_root_override = os.environ.get("WIELDER_STAGE_ROOT")
    if stage_root_override:
        stage_root = Path(stage_root_override).expanduser()
    else:
        home = Path.home()
        stage_root = home / "stage" / project_name
    stage_root.mkdir(parents=True, exist_ok=True)
    
    user, machine = get_whoami()

    # 2. Base Runtime Defaults
    super_repo_root = project_root_path.parent
    
    # Initialize Git Snapshot
    git_snapshot = _git_snapshot_injection(super_repo_root)

    local_system = wu.get_local_system()
    host_mount_prefix = "" #wu.get_os_host_mount_prefix(local_system)

    default_dict = {
        "project_root": project_root_path.as_posix(),
        "conf_root": conf_root_path.as_posix(),
        "super_repo_root": super_repo_root.as_posix(),
        "stage_root": stage_root.as_posix(),
        "context_conf": context_conf_name,
        "user": user,
        "machine": machine,
        "local_system": local_system,
        "host_mount_prefix": host_mount_prefix,
        "test": False,
    }
    # Merge Git info into defaults
    default_dict.update(git_snapshot)
    default_dict["git"]["short_commit"] = str(default_dict["git"]["commit"])[:8]
    
    if runtime_defaults:
        default_dict.update(runtime_defaults)
        
    base_defaults = ConfigFactory.from_dict(default_dict)

    # 3. Load Base Project Config
    project_conf = _parse_hocon(conf_root_path / "project.conf").with_fallback(base_defaults, resolve=False)

    # 4. Resolve Global Ecosystem Master Configuration
    # Single entry point for global concerns (network, git policy, etc.)
    super_module_path = super_repo_root / "conf" / "super_module.conf"
    if super_module_path.exists():
        # HOCON 'include' statements inside super_module.conf are resolved relative to its directory
        project_conf = _parse_hocon(super_module_path).with_fallback(project_conf, resolve=True)

    # 5. Native Ecosystem CLI Parser (Absolute Primacy Layer 6)
    
    cli_args, _ = parse_known_args_strict(get_ecosystem_parser())
    cli_dict = normalize_cli_overrides(vars(cli_args))

    if cli_overrides:
        cli_dict.update(normalize_cli_overrides(cli_overrides))

    context_conf_name = cast(str, cli_dict.get("context_conf", context_conf_name))
    test_mode = _is_enabled_mode(cli_dict.get("test", default_dict.get("test")), default=False)
    cli_conf = ConfigFactory.from_dict(cli_dict)

    # 6. Central Context Packs (Tier 5)
    context_root = project_root_path.parent / "context_conf" / context_conf_name
    for overlay in ["secrets.conf", "agents.conf", "developer.conf", "ephemeral.conf"]:
        overlay_path = context_root / overlay
        if overlay_path.exists():
            context_overlays = context_overlays.with_fallback(_parse_hocon(overlay_path), resolve=False)

    # 7. Extract routing identifiers from CLI/defaulted CLI only.
    ecosystem = cli_dict["ecosystem"] if "ecosystem" in cli_dict else project_conf.ecosystem
    stage_tier = cli_dict["stage_tier"] if "stage_tier" in cli_dict else project_conf.stage_tier
    security = cli_dict["security"] if "security" in cli_dict else project_conf.security
    destroy = cli_dict["destroy"] if "destroy" in cli_dict else project_conf.destroy
    canary = cli_dict["canary"] if "canary" in cli_dict else project_conf.canary

    # 8. Compose the Final Configuration Tree in Strict Architecture Primacy:
    # CLI Overrides > test > context_conf > security > stage_tier > ecosystem > destroy > canary > project.conf
    final_conf = project_conf
    
    canary_path = conf_root_path / "canary" / canary / "canary.conf"
    if canary_path.exists():
        canary_conf = _parse_hocon(canary_path)
        final_conf = canary_conf.with_fallback(final_conf, resolve=False)

    destroy_path = conf_root_path / "destroy" / destroy / "destroy.conf"
    if destroy_path.exists():
        destroy_conf = _parse_hocon(destroy_path)
        final_conf = destroy_conf.with_fallback(final_conf, resolve=False)

    ecosystem_path = resolve_ecosystem_manifest_path(conf_root_path / "ecosystem", str(ecosystem))
    if ecosystem_path is not None:
        manifest = _parse_hocon(ecosystem_path)
        final_conf = manifest.with_fallback(final_conf, resolve=False)

    stage_tier_path = conf_root_path / "stage_tier" / stage_tier / "tier.conf"
    if stage_tier_path.exists():
        tier_conf = _parse_hocon(stage_tier_path)
        final_conf = tier_conf.with_fallback(final_conf, resolve=False)
        
    security_path = conf_root_path / "security" / security / "security.conf"
    if security_path.exists():
        security_conf = _parse_hocon(security_path)
        final_conf = security_conf.with_fallback(final_conf, resolve=False)

    context_conf_path = conf_root_path / "context_conf" / context_conf_name
    ephemeral_path = context_conf_path / "ephemeral.conf"

    if ephemeral_path.exists():
        ephemeral_conf = _parse_hocon(ephemeral_path)
        final_conf = ephemeral_conf.with_fallback(final_conf, resolve=False)

    # Developer config is explicit local operator intent and must trump generated ephemeral state.
    developer_path = context_conf_path / "developer.conf"
    
    if developer_path.exists():
        developer_conf = _parse_hocon(developer_path)
        final_conf = developer_conf.with_fallback(final_conf, resolve=False)

    final_conf = context_overlays.with_fallback(final_conf, resolve=False)

    test_conf_path = None
    ecosystem_test_conf_path = resolve_ecosystem_conf_path(
        conf_root_path / "test",
        str(ecosystem),
        "test.conf",
    )
    if test_mode and ecosystem_test_conf_path is not None:
        test_conf_path = ecosystem_test_conf_path
        final_conf = _parse_hocon(test_conf_path).with_fallback(final_conf, resolve=False)

    final_conf = cli_conf.with_fallback(final_conf, resolve=False)
    context_path_conf = ConfigFactory.from_dict(
        {
            "conf_root": conf_root_path.as_posix(),
            "context_conf_root": context_conf_path.as_posix(),
            "ephemeral_conf_path": ephemeral_path.as_posix(),
            "developer_conf_path": developer_path.as_posix(),
            "test_conf_path": test_conf_path.as_posix() if test_conf_path is not None else "",
        }
    )
    final_conf = context_path_conf.with_fallback(final_conf, resolve=False)
    


    # Topological Guardrail: Resolution test assertion
    if final_conf.get_bool("resolution_test", False):
        pass
    # 8. Resolve Substitutions Now That Overlays Are Final
    project_conf = ConfigFactory.from_dict({}).with_fallback(final_conf, resolve=resolve)

    #TODO move this to callers
    # 7. Post-Processing: Parse agent_id and Validate Journey (Only if Resolved)
    if resolve:
        if "agent_id" in project_conf:
            # Pattern: <user>_<machine>_<type>_<index>
            parts = project_conf.agent_id.split('_')
            if len(parts) >= 4:
                agent_meta = {
                    "agent": {
                        "user": parts[0],
                        "machine": parts[1],
                        "type": parts[2],
                        "index": int(parts[3])
                    }
                }
                project_conf = ConfigFactory.from_dict(agent_meta).with_fallback(project_conf, resolve=True)

        # 8. Aggressive Validation of the Journey Plot
        if "git" in project_conf and "active_feature" in project_conf.git:
            if project_conf.git.active_feature == "dev/initial/main":
                raise AttributeError(
                    "\n\033[1;31m[CRITICAL] Journey Not Plotted!\033[0m\n"
                    "You are using the default 'dev/initial/main' feature state.\n"
                    "Please declare your active journey in 'context_conf/default_conf/developer.conf':\n\n"
                    "git.active_feature = \"feature/your-feature-name/main\"\n"
                )

    return project_conf

def get_agent_id(conf: ConfigTree) -> str:
    """Returns the fully qualified agent ID."""
    return conf.agent_id

def get_agent_ips(conf: ConfigTree, domain: str) -> dict:
    """
    Calculates deterministic ports based on the Global Network Grid Map.
    Final_Port = Base + Agent_Type_Offset + Domain_Offset + Instance_Index
    """
    try:
        agent_type = conf.agent.type
        agent_index = int(conf.agent.index)
        
        net = conf.network
        base_api = int(net.port_prefix.api) * 1000
        base_gui = int(net.port_prefix.gui) * 1000
        
        type_offset = int(net.agent_id[agent_type]) * 10
        domain_offset = int(net.domain_id[domain]) * 100
        
        api_port = base_api + domain_offset + type_offset + agent_index
        gui_port = base_gui + domain_offset + type_offset + agent_index
        
        # Inject back into the config tree for downstream get_api_url usage
        if "network" in conf and "domains" in conf.network and domain in conf.network.domains:
            domain_conf = conf.network.domains[domain]
            domain_conf.api.put("port", api_port)
            domain_conf.gui.put("port", gui_port)

        return {
            "api": {"host": "0.0.0.0", "port": api_port},
            "gui": {"host": "0.0.0.0", "port": gui_port}
        }
    except Exception as e:
        raise AttributeError(f"Failed to calculate agent IPs for domain '{domain}'. "
                             f"Ensure agent_id and network.conf are correctly configured. Error: {e}")


def get_wield_app_conf(
    project_root: str,
    conf_root: str,
    app_name: str,
    project_name: str = "culture",
    runtime_defaults: dict = None,
    cli_overrides: dict | None = None,
    app_conf_root: str = None,
    module_paths: list[str] = None,
    mute: bool = False,
    resolve: bool = True,
) -> TypedConfig:
    """
    Core Wielder App Configuration Loader.
    Loads raw project defaults, merges app-specific HOCON, and executes a unified resolution pass.
    """
    # 1. Get RAW, unresolved project config first
    project_conf = get_wield_project_conf(
        project_root=project_root,
        conf_root=conf_root,
        project_name=project_name,
        runtime_defaults=runtime_defaults,
        cli_overrides=cli_overrides,
        resolve=False
    )

    # 2. Load RAW App Config
    target_app_root = app_conf_root if app_conf_root else conf_root
    app_conf_path = resolve_app_conf_path(Path(target_app_root) / "apps", app_name, required=True)
    app_conf = _parse_hocon(app_conf_path)

    app_test_conf_path = app_conf_path.parent / "test.conf"
    if _is_enabled_mode(project_conf.get("test", False), default=False) and app_test_conf_path.exists():
        app_test_conf = _parse_hocon(app_test_conf_path)
        app_conf = app_test_conf.with_fallback(app_conf, resolve=False)
    
    # 3. Merge Raw Project Tree on top of App Config (Developer > Security > Stage Tier > Ecosystem > App)
    merged = project_conf.with_fallback(app_conf, resolve=False)

    #TODO rethink this!!!!
    # 3.5 Dynamic Module / Wield Arrays
    if module_paths:
        for m_path in module_paths:
            if wu.exists(m_path):
                override = _parse_hocon(Path(m_path))
                merged = override.with_fallback(merged, resolve=False)

    if resolve:
        resolved_conf = ConfigFactory.from_dict({}).with_fallback(merged, resolve=True)
        log_wielder_modes(resolved_conf, app_name, mute=mute)
        return resolved_conf

    return merged
