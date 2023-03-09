#!/usr/bin/env python
import logging

from wielder.util.log_util import setup_logging
from wielder.wield.project import get_super_project_wield_conf, default_conf_root, DEFAULT_WIELDER_APP
from wielder.wield.wield_service import get_module_root

if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    project_conf_dir = default_conf_root()

    conf = get_super_project_wield_conf(project_conf_dir, app=DEFAULT_WIELDER_APP, configure_wield_modules=True)

    print("hi")


