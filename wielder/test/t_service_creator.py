#!/usr/bin/env python
import logging

from wielder.util.log_util import setup_logging
from wielder.util.service_creator import create_module_from_module
from wielder.wield.project import default_conf_root, get_super_project_wield_conf, DEFAULT_WIELDER_APP

if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    project_conf_dir = default_conf_root()
    conf = get_super_project_wield_conf(project_conf_dir, app=DEFAULT_WIELDER_APP, configure_wield_modules=True)

    create_module_from_module(conf)



