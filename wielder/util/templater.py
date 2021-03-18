#!/usr/bin/env python
import logging
import os
import jprops
from jprops import _CommentSentinel
from pyhocon import ConfigTree

from wielder.util.arguer import get_kube_parser, process_args, Conf


# TODO Consider switching from tuples to dict
from wielder.util.log_util import setup_logging


def get_template_var_by_key(template_variables, key):

    for r in template_variables:

        if r[0] == key:

            return r


def gather_templates(dir_path, conf):
    """
    This function produces a list of full paths of files ending with .tmpl from all sub  directories that are not ignored in conf
    :param dir_path: Path to the directory to be purged
    :return: None
    """
    template_files = []

    for subdir, dirs, files in os.walk(dir_path):
        logging.debug(f"dirs: \n{dirs}")

        dir_name = subdir[subdir.rfind('/') + 1:]

        if dir_name not in conf.template_ignore_dirs:
            logging.info(f"searching in dir_name: {dir_name}")

            for file in files:
                logging.debug(f"file: {os.path.join(subdir, file)}")
                file_path = subdir + os.sep + file

                if file_path.endswith(".tmpl"):

                    template_files.append(file_path)
        else:
            logging.info(f"ignoring dir_name: {dir_name}")

    return template_files


def remove_non_templates(dir_path, conf):
    """
    This function will delete files ending with .yaml .json from all sub  directories that are not ignored in conf
    :param dir_path: Path to the directory to be purged
    :return: None
    """

    for subdir, dirs, files in os.walk(dir_path):
        logging.debug(f"dirs: \n{dirs}")

        dir_name = subdir[subdir.rfind('/') + 1:]

        if dir_name not in conf.template_ignore_dirs:
            logging.info(f"searching in dir_name: {dir_name}")

            for file in files:
                logging.debug(f"file: {os.path.join(subdir, file)}")
                full_path = subdir + os.sep + file

                if full_path.endswith(".yaml") or full_path.endswith(".json"):

                    os.remove(full_path)
        else:
            logging.info(f"ignoring dir_name: {dir_name}")

    return None


def templates_to_instances(file_paths, tmpl_vars):
    """
    This function renders a list of files ending with .tmpl into files without .tmpl ending,
    replacing template_variables from conf. if such files exist before hand they are deleted
    :param tmpl_vars: variables declared in config file to be replaced in rendered template.
    :param file_paths: Path to the directory to be purged
    :return: None
    """
    for file_path in file_paths:

        logging.info(f"file path: {file_path}")

        yaml_file = file_path.replace('.tmpl', '')

        try:
            os.remove(yaml_file)
        except OSError:
            pass

        with open(file_path, "rt") as file_in:

            with open(yaml_file, "wt") as file_out:

                for line in file_in:

                    if '#' in line:

                        for r in tmpl_vars:
                            if r[0] in line:

                                logging.info(f"line: {line}     replacing {r[0]} with {r[1]}")
                                line = line.replace(r[0], f'{r[1]}')

                                if '#' not in line:
                                    break

                    file_out.write(line)


def prop_templates_to_instances(var_file_path, template_files, print_variables=False):
    """
    This function renders a list of files ending with .tmpl into files without .tmpl ending,
    replacing template_variables from conf. if such files exist before hand they are deleted
    :param var_file_path:
    :param template_files:
    :param print_variables:
    :return:
    """
    with open(var_file_path) as fp:

        variable_map = jprops.load_properties(fp)

        if print_variables:

            tuple_list_vars = jprops.iter_properties(fp, comments=False)

            logging.info(f'\n\nproperties:\n')

            for prop in list(tuple_list_vars):

                logging.info(prop)

    for template_file in template_files:

        prop_file = template_file.replace('.tmpl', '')

        try:
            os.remove(prop_file)
        except OSError:
            pass

        with open(template_file, "rt") as file_in:

            props = list(jprops.iter_properties(file_in, comments=True))

            with open(prop_file, "wt") as file_out:

                for prop in props:

                    logging.info(f'prop: {prop}   of type:  {type(prop[0])}')

                    if not isinstance(prop[0], _CommentSentinel):

                        new_prop = prop[1]

                        if '#' in prop[1]:

                            logging.debug(prop)
                            vrs = get_vars_from_string(prop[1], '#')
                            logging.debug(vrs)

                            new_val = prop[1]

                            for k in vrs:
                                logging.debug(f'key: {k}    value:{variable_map[k]}')
                                new_val = new_val.replace(k, variable_map[k])

                            new_val = new_val.replace('#', '')
                            new_prop = new_val

                        new_prop = new_prop.replace('"', '')

                        file_out.write(f"{prop[0]}={new_prop}\n")
                    else:
                        file_out.write(f"\n\n#  {prop[1]}\n")


def add_props_file(base_path, addition_path):

    with open(addition_path, "rt") as file_in:

        props = list(jprops.iter_properties(file_in, comments=True))

    with open(base_path, "a") as file_out:

        for prop in props:

            if not isinstance(prop[0], _CommentSentinel):

                file_out.write(f"{prop[0]}={prop[1]}\n")

            else:
                file_out.write(f"\n\n#  {prop[1]}\n")


def add_props(base_path, props, comment):

    with open(base_path, "a") as file_out:

        if comment is not None:

            file_out.write(f"# {comment}\n")

        for k, v in props.items():

            if v is not None:

                file_out.write(f"{k}={v}\n")


def get_vars_from_string(s, c):

    indexes = [pos for pos, char in enumerate(s) if char == c]

    indexes_length = len(indexes) - len(indexes) % 2

    b = []

    if indexes_length == 0:
        return b

    i = 1
    while i < indexes_length:
        b.append(s[indexes[i-1] + 1: indexes[i]])
        i += 2

    return b


def get_raw_arg(conf, key, default_value=None):

    try:
        default_value = conf.raw_config_args[key]
    except:
        logging.error()
        pass

    return default_value


def config_tree_to_tuple(tree, print_vars=True, template=True, escape_sequence='#'):
    """
    A utility for turning a dictionary to to a flate list od tuples
    One use is to convert a pyhocon ConfigFactory to a templater usable list of tuples
    :param escape_sequence: the template escape sequence by default #var#
    :param template: should add template escape sequence to key
    :param print_vars: should print or not
    :param tree: ConfigFactory or dictionary
    :return: list of tuples rendered from input tree
    """

    template_variables = []

    logging.debug(f'type(tree): {type(tree)}')

    for k in tree:

        v = tree[k]

        if template:
            k = f"{escape_sequence}{k}{escape_sequence}"

        if print_vars:
            logging.info(f"k: {k}   v: {v}")

        template_variables.append((k, v))

    return template_variables


def config_to_terraform(tree, destination, name='terraform.tfvars', print_vars=True):
    """
    TODO support terraform dictionary and list depth
    Take a pyhocon tree and converts it to a terraform file
    :param tree: pyhocon tree
    :param destination:
    :param name:
    :param print_vars: should print vars to console
    :return: nothing
    """

    config_file = f"{destination}/{name}"

    try:
        os.remove(config_file)
    except OSError:
        pass

    with open(config_file, "a") as file_out:

        hocon_to_terraform_syntax(tree, file_out, print_vars)

        file_out.write(f'\n\n')


def hocon_to_terraform_syntax(tree, file_out, print_vars, indent=''):

    for k in tree:

        v = tree[k]

        if print_vars:
            logging.info(f"k: {k}   v: {v}")

        if isinstance(v, ConfigTree):

            file_out.write(f"{k} = " + '{\n')
            hocon_to_terraform_syntax(v, file_out, print_vars, f'  {indent}')
            file_out.write('}\n\n')
            continue

        elif isinstance(v, str):
            v = f'"{v}"'
        elif isinstance(v, bool):
            v = f'{v}'.lower()
        elif isinstance(v, list):
            v = f"{v}".replace("'", '"')
        elif isinstance(v, dict):
            # TODO check dictionaries
            v = f"{v}".replace("'", '"')

        file_out.write(f'{indent}{k} = {v}\n\n')


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    dir_path = os.path.dirname(os.path.realpath(__file__))
    logging.debug(f"current working dir: {dir_path}")

    conf = Conf()
    conf.template_variables = [
        ("#yo#", "Goofy"),
        ("#bro#", "Joker")
    ]

    templates = gather_templates(dir_path, conf)

    logging.info(f"templates:\n{templates}")
    templates_to_instances(templates, conf.template_variables)


