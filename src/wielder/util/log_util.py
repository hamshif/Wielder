#!/usr/bin/env python
import logging

import os
import logging.config

import yaml


def setup_logging(
        default_path='logging.yaml',
        default_level=None,
        env_key='LOG_CFG'
):
    """
    Setup logging configuration
    """
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = yaml.safe_load(f.read())

        logging.config.dictConfig(config)
    else:
        default_level = logging.INFO if default_level is None else default_level
        logging.basicConfig(level=default_level)


if __name__ == "__main__":

    setup_logging(
        default_level=logging.DEBUG
    )

    logging.info('Configured logging')
    logging.debug('Configured logging')
    print('psyche')
