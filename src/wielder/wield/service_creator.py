#!/usr/bin/env python

from wielder.util.arguer import replace_none_vars_from_args
from wielder.wield.wield_service import WieldService, get_module_root
from wielder.wield.wielder_project_locale import Locale


def get_locale(__file__1, project_root=None, super_project_root=None):

    module_root = get_module_root(__file__1)
    print(f"Module root: {module_root}")

    if not project_root:
        project_root = module_root
    if not super_project_root:
        super_project_root = project_root.replace('/Wielder/src/wielder/', '')

    locale = Locale(
        project_root=project_root,
        super_project_root=super_project_root,
        module_root=module_root,
        code_path=None
    )

    return locale


def create_service(action=None, auto_approve=False, service_only=False):

    locale = get_locale(__file__)

    action, mode, enable_debug, local_mount, service_mode = replace_none_vars_from_args(
        action=action,
        mode=None,
        enable_debug=None,
        local_mount=None,
        service_mode=None,
        project_override=None
    )

    print('break')


if __name__ == "__main__":

    create_service()
