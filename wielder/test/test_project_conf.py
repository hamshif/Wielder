#!/usr/bin/env python
import logging

from wielder.util.log_util import setup_logging
from wielder.wield.project import get_super_project_wield_conf
from wielder.wield.wield_service import get_module_root

if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    p = get_module_root()

    p = p[:p.rfind('/')]

    project_conf_dir = f'{p}/conf'

    app = 'snegurochka'

    conf = get_super_project_wield_conf(project_conf_dir, app=app, configure_wield_modules=False)

    print("hi")


