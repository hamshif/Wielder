import logging

import json
from pprint import pprint

import yaml
import pyhocon
from pyhocon.tool import HOCONConverter as Hc
from pyhocon import ConfigFactory as Cf


def wrap_included(paths):
    """
    Creates configuration tree includes string on the fly
    :param paths: A list of file paths
    :return: A string usable by pyhocon.ConfigFactory.parse_string to get config tree
    """

    includes = ''
    for path in paths:
        includes += f'include file("{path}")\n'

    return includes


def inject_vars(base, injection):
    """
    Adds variables to a hocon parsable string on the fly
    :param base:
    :param injection: A list of file variables to inject into hocon parsable string
    :return: A string usable by pyhocon.ConfigFactory.parse_string to get config tree
    """

    for k, v in injection.items():

        if isinstance(v, dict):
            b = '{'
            e = '}'

            base += f'\n{k}: {b}\n   '
            base = inject_vars(base, v)
            base += f'\n   {e}'
        else:
            base += f'\n{k}: {v}'

    return base


# TODO deprecate and use resolve_ordered!!!
def get_conf_ordered_files(ordered_conf_files, injection={}, injection_str=''):
    """
    give a list of ordered configuration files creates a config-tree
    :param injection_str: a hocon valid string
    :param injection: a dictionary of variables to override hocon file variables on the fly.
    :param ordered_conf_files:
    :return:
    """

    conf_include_string = wrap_included(ordered_conf_files) + f'\n{injection_str}\n'

    conf_include_string = inject_vars(conf_include_string, injection)

    logging.info(f"\nconf_include_string:\n{conf_include_string}\n")

    conf = Cf.parse_string(conf_include_string)

    logging.info(f'conf Hocon object:\n{conf}')

    return conf


def resolve_ordered(ordered_conf_paths, injection=None, cmd_args=None, show=True):
    """
    Resolves a list of Hocon configuration files and optional dictionary and argparse 
    precedence: args, injection, first to last in list
    :param ordered_conf_paths: Paths to hocon config files
    :param injection: A dictionary of values
    :param cmd_args: commandline args from argparse
    :param show: print config
    :return: resolved hocon ConfigTree
    """

    if injection is None:

        injection = {}

    if cmd_args is not None:

        ar = vars(cmd_args)
        injection = {**injection,  **ar}

    base_conf = Cf.from_dict(injection)

    last_path = ordered_conf_paths[-1]

    files_conf = Cf.parse_file(last_path, resolve=False)

    for ff in reversed(ordered_conf_paths[:-1]):

        files_conf = files_conf.with_fallback(
            config=ff,
            resolve=False,
        )

    conf = base_conf.with_fallback(
        config=files_conf,
        resolve=True,
    )

    if show:
        for i in conf.items():
            print(i)

    return conf


def yaml_file_to_hocon(src_path):

    with open(src_path, 'r') as yaml_in:

        from_yaml = yaml.safe_load(yaml_in)
        json_string = json.dumps(from_yaml)
        hocon_object = pyhocon.ConfigFactory.parse_string(json_string)
        return hocon_object


def hocon_to_file(src_path):

    conf = yaml_file_to_hocon(src_path)
    hocon_dest = src_path.replace('.yaml', '.conf')

    with open(hocon_dest, 'w') as file_hocon:

        file_hocon.write(Hc().to_hocon(conf))

    return hocon_dest


basic_native_types = (str, int, float, bool)


def conf_to_native(conf, vessel={}):
    """
    Converts Hocon Tree to basic native types.
    Uses tail recursion.
    Best used without specifying vessel.
    :param conf:
    :param vessel: The dict to be returned Defaults to
    :return: vessel with native fields extracted from Hocon
    """

    for k in conf:
        v = conf[k]
        if type(v) in basic_native_types or type(v) == list:
            vessel[k] = v
        else:
            vessel[k] = conf_to_native(v)

    return vessel

