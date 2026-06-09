#!/usr/bin/env python
import logging
import json

from wielder.util.log_util import setup_logging
from wielder.util.wgit import WGit
from wielder.wield.project import get_super_project_wield_conf, default_conf_root, DEFAULT_WIELDER_APP


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    project_conf_dir = default_conf_root()

    conf = get_super_project_wield_conf(project_conf_dir, app=DEFAULT_WIELDER_APP, configure_wield_modules=True)

    wg = WGit(conf.super_project_root)

    info = wg.as_dict_injection()
    info = json.dumps(info, indent=4)

    print(f"info:\n{info}")


