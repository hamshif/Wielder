#!/usr/bin/env python

from wielder.util.arguer import replace_none_vars_from_args
from wielder.util.templater import replace_all_in_file, variation_copy_dir
from wielder.util.util import replace_last
from wielder.wield.enumerator import Languages
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


def create_service_infrastructure_code(name='micro', destination=None, namespace='default', lang=Languages.PYTHON, action=None, service_only=False):
    '''
    Creates a Wielder ops folder complete with everything needed for local and cloud operational Kubernetes deployment
    (configmap, storage, service ...) & image packing.
    :param name: The name of the service should be unique to you project
    :param destination: Destination folder.
    :param namespace: Kubernetes namespace.
    :param lang: Choice of supported language
    :param action:
    :param service_only:
    :return:
    '''

    locale = get_locale(__file__1=__file__, project_root=destination)

    action, mode, enable_debug, local_mount, service_mode = replace_none_vars_from_args(
        action=action,
        mode=None,
        enable_debug=None,
        local_mount=None,
        service_mode=None,
        project_override=None
    )

    print('break')

    _new = 'micro'
    _old = 'boot'

    origin_path = '/Users/gideonbar/dev/data/wield-services/src/wield_services/deploy/boot'

    destination_path = replace_last(origin_path, 'boot', 'micro')

    destination_path = f'/Users/gideonbar/dev/{_new}'

    variation_copy_dir(origin_path, destination_path, _old=_old, _new=_new)


if __name__ == "__main__":

    create_service_infrastructure_code()
