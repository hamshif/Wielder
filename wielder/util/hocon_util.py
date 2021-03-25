import logging

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
        base += f'\n{k}: {v}'

    return base


def get_conf_ordered_files(ordered_conf_files, injection={}):
    """
    give a list of ordered configuration files creates a config-tree
    :param injection: a dictionary of variables to override hocon file variables on the fly.
    :param ordered_conf_files:
    :return:
    """

    conf_include_string = wrap_included(ordered_conf_files)

    conf_include_string = inject_vars(conf_include_string, injection)

    logging.info(f"\nconf_include_string:\n{conf_include_string}\n")

    conf = Cf.parse_string(conf_include_string)

    logging.info(f'conf Hocon object:\n{conf}')

    return conf

