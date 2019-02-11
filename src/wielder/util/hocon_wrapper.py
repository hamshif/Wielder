#!/usr/bin/env python

import os
from pyhocon import ConfigFactory as Cf
from wielder.util.util import line_prepender


def include_configs(base_path, included_paths):

    for included_path in included_paths:

        line_prepender(filename=base_path, line=f'include file("{included_path}")')

    return Cf.parse_file(base_path)


if __name__ == "__main__":

    dir_path = os.path.dirname(os.path.realpath(__file__))
    print(f"current working dir: {dir_path}")

    dir_path = ''

    _base_path = f'{dir_path}example.conf'
    _included_files = [f'{dir_path}example1.conf', f'{dir_path}example2.conf']

    _conf = include_configs(base_path=_base_path, included_paths=_included_files)

    print('break point')
