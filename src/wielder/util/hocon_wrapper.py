#!/usr/bin/env python

import os
from pyhocon import ConfigFactory as Cf
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

        line_prepender(filename=base_path, line=f'include file("{included_path}")', once=False)

    conf = Cf.parse_file(base_path)

    if remove_includes:

        for included_path in included_paths:

            remove_line(base_path, included_path)

    return conf


if __name__ == "__main__":

    dir_path = os.path.dirname(os.path.realpath(__file__))
    print(f"current working dir: {dir_path}")

    dir_path = ''

    _base_path = f'{dir_path}example.conf'
    _included_files = [f'{dir_path}example1.conf']

    _conf = include_configs(base_path=_base_path, included_paths=_included_files)

    print('break point')
