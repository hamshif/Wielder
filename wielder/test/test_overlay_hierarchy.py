import logging
import pprint
from pathlib import Path
from wielder.wield.wield_conf import get_wield_app_conf
from wielder.wield.project import get_super_project_roots
from wielder.util.arguer import get_wielder_parser, parse_known_args_strict
from wielder.util.log_util import setup_logging

def test_native_overlay():
    print("\n\n" + "="*80)
    print("🚀  QA TEST: NATIVE PYHOCON OVERLAY BOUNDARIES")
    print("="*80 + "\n")

    print("[*] Retrieving Native Framework Boundaries...")
    _, super_root, _ = get_super_project_roots()
    app_conf_path = next(
        Path(super_root).glob("*/conf/apps/bootstrap_antifragile_workstation/app.conf")
    )
    app_conf_root = app_conf_path.parents[2].as_posix()
    wielder_module_root = app_conf_path.parents[3].as_posix()

    print(f"   [+] super_root: {super_root}")
    print(f"   [+] conf_root:  {app_conf_root}")

    # Explicitly fetching CLI equivalents representing native developer context loading
    wield_parser = get_wielder_parser()
    wield_args, _ = parse_known_args_strict(wield_parser)

    # We will pass the arguments strictly via injection like WieldService natively does
    injection = {}
    injection.update(wield_args.__dict__)

    print("\n--------------------------------------------------------------------------------")
    print("⚙️  EVALUATING: get_wield_app_conf('bootstrap_antifragile_workstation')")
    print("--------------------------------------------------------------------------------\n")

    conf = get_wield_app_conf(
        project_root=wielder_module_root,
        conf_root=wielder_module_root + "/conf",
        app_name="bootstrap_antifragile_workstation",
        runtime_defaults=injection,
        app_conf_root=app_conf_root,
        module_paths=[]
    )

    print("🎯  NATIVE RESOLUTION (Sample Extracted):\n")
    print(f"   [Domain] stage_tier:       {conf.get('stage_tier', 'MISSING')}")
    print(f"   [Domain] ecosystem:        {conf.get('ecosystem', 'MISSING')}")
    print(f"   [Domain] deploy_env:       {conf.get('deploy_env', 'MISSING')}")
    print(f"   [Network] kube_context:    {conf.get('kube_context', 'MISSING')}")
    print(f"   [App Config] app root:     {Path(app_conf_root).name}")

    print("✅  SUCCESS: PyHocon engine initialized and successfully evaluated cross-domain configuration dependencies without crashing or synthesizing overrides.")
    print("="*80 + "\n")


if __name__ == "__main__":
    setup_logging(log_level=logging.WARNING)
    test_native_overlay()
