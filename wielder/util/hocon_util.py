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


def get_conf_ordered_files(ordered_conf_files):
    """
    give a list of ordered configuration files creates a config-tree
    :param ordered_conf_files:
    :return:
    """

    conf_include_string = wrap_included(ordered_conf_files)

    logging.info(f"\nconf_include_string:  {conf_include_string}\n")

    conf = Cf.parse_string(conf_include_string)

    logging.info(f'conf Hocon object:\n{conf}')

    return conf

