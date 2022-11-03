#!/usr/bin/env python
import logging

from wielder.util.log_util import setup_logging
from wielder.wield.project import get_super_project_conf

if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    conf_dir = f'Wielder/conf'

    conf = get_super_project_conf(conf_dir)

    print("hi")


