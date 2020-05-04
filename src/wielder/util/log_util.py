#!/usr/bin/env python
import logging
import logging.config
import os
import yaml


def setup_logging(
        default_path='logging.yaml',
        log_level=None,
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
        log_level = logging.INFO if log_level is None else log_level
        # logging.basicConfig(level=log_level)

    if log_level is not None:
        logger = logging.getLogger()
        logger.setLevel(log_level)

        for handler in logger.handlers:
            handler.setLevel(log_level)


if __name__ == "__main__":

    setup_logging(
        log_level=logging.DEBUG
    )

    logging.info('Configured logging')
    logging.debug('Configured logging')
