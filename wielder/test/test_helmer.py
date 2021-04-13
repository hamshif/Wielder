#!/usr/bin/env python

import os
import logging

from wield_services.wield.deploy.util import get_locale

from wielder.util.log_util import setup_logging
from wielder.wield.helmer import WrapHelm
from wielder.wield.enumerator import HelmCommand

if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    logging.debug('Configured logging')

    locale = get_locale(__file__)

    test_root = f'{locale.module_root}/test'

    os.system(f'ls -la {test_root}')

    repo = 'bitnami'
    repo_url = 'https://charts.bitnami.com/bitnami'
    chart = 'cassandra'
    namespace = 'cassandra'
    release = 'cassandra'
    values_path = f'{test_root}/helm_cassandra.yaml'

    wh = WrapHelm(
        repo=repo,
        repo_url=repo_url,
        chart=chart,
        release=release,
        namespace=namespace,
        values_path=values_path
    )

    wh.wield(HelmCommand.INIT_REPO, True)
