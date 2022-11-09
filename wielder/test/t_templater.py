#!/usr/bin/env python
import logging
import os

from wielder.util.arguer import Conf
from wielder.util.log_util import setup_logging
from wielder.util.templater import gather_templates, templates_to_instances

if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    _dir_path = os.path.dirname(os.path.realpath(__file__))
    logging.debug(f"current working dir: {_dir_path}")

    _conf = Conf()
    _conf.template_variables = [
        ("#yo#", "Goofy"),
        ("#bro#", "Joker")
    ]

    _templates = gather_templates(_dir_path, _conf)

    logging.info(f"templates:\n{_templates}")
    templates_to_instances(_templates, _conf.template_variables)
