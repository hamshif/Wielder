#!/usr/bin/env python
import logging

from wield_services.wield.deploy.util import get_project_locale
from wield_services.wield.log_util import setup_logging

from wielder.util.wgit import WGit


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    logging.debug('break point')

    locale = get_project_locale(__file__)

    wg = WGit(locale.super_project_root)

    wg.get_submodule_commit('dud')
