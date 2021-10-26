#!/usr/bin/env python
import logging
from time import sleep

from wielder.util.commander import async_cmd
from wielder.util.log_util import setup_logging


def is_docker_running():

    r = async_cmd('docker stats --no-stream')

    if 'Cannot' in r[0] or 'Error' in r[0]:

        logging.warning('docker is not running')

        return False
    else:
        logging.info('docker is running')
        return True


def make_sure_docker_is_running():

    if not is_docker_running():

        async_cmd('open /Applications/Docker.app')

        waited = 0

        while not is_docker_running():

            logging.info(f'waited {waited} for docker to run')
            waited = waited + 10
            sleep(10)


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    logging.debug('Configured logging')

    make_sure_docker_is_running()

