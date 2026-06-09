#!/usr/bin/env python
import logging
import os
from pyhocon import ConfigFactory as Cf

from wielder.util.log_util import setup_logging
from wielder.util.util import line_prepender, remove_line


def include_configs(base_path, included_paths, remove_includes=True):
    """
    includes a list of file paths in pyhocon ConfigTree
    :param remove_includes: if True this removes the includes from the config file after parsing it with them
    :param base_path: the basic config file
    :param included_paths: a list of paths to include in the tree
    :return: combined ConfigTree
    """

    for included_path in included_paths:

        line = f'include file("{included_path}")'
        # logging.debug(f'Trying to add {line} to {base_path}')
        line_prepender(filename=base_path, line=line, once=True)
        logging.info(f'Added {line} to {base_path}')

    # logging.debug(f'Trying to parse {base_path}')
    conf = Cf.parse_file(base_path)
    # logging.debug(f'parsed {base_path}')

    if remove_includes:

        for included_path in included_paths:

            remove_line(base_path, included_path)

    return conf


if __name__ == "__main__":

    setup_logging(
        log_level=logging.DEBUG
    )

    dir_path = os.path.dirname(os.path.realpath(__file__))
    logging.debug(f"current working dir: {dir_path}")

    dir_path = ''

    _base_path = f'{dir_path}example.conf'
    _included_files = [f'{dir_path}example1.conf']

    _conf = include_configs(base_path=_base_path, included_paths=_included_files)

    logging.debug('break point')
