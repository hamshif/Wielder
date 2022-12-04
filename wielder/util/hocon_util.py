import json
import logging
import os

import pyhocon
import yaml
from pyhocon import ConfigFactory as Cf
from pyhocon.tool import HOCONConverter as Hc


def object_to_conf(obj):

    v = vars(obj)
    conf = Cf.from_dict(v)
    return conf


def resolve_ordered(ordered_conf_paths, injection=None, cmd_args=None, show=False):
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
        # TODO replace with new ** with |= when Wielder supports the new python 3.10
        # injection |= ar
        injection = {**injection,  **ar}

    base_conf = Cf.from_dict(injection)

    last_path = ordered_conf_paths[-1]

    if os.path.isfile(last_path):

        files_conf = Cf.parse_file(last_path, resolve=False)
    else:
        logging.warning(f"Couldn't find file\n{last_path}")
        files_conf = Cf.from_dict({})

    for ff in reversed(ordered_conf_paths[:-1]):

        if os.path.isfile(ff):

            logging.info(f'Latest hocon config file to be read:\n{ff}')

            files_conf = files_conf.with_fallback(
                config=ff,
                resolve=False,
            )
        else:
            logging.warning(f"Couldn't find file\n{ff}")

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

