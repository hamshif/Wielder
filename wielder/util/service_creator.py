#!/usr/bin/env python
import logging
import os
from shutil import copyfile


def has_end(whole, ends):

    for end in ends:

        if whole.endswith(end):

            return True

    return False


def variation_copy_dir(origin_path, dest_path, origin_name, target_name, ignored_dirs,
                       ignored_files, replace_in_copy=True):
    """

    :param replace_in_copy:
    :param ignored_files:
    :param ignored_dirs:
    :param origin_path:
    :param dest_path:
    :param origin_name:
    :param target_name:
    :return:
    """

    dest_module_path = f'{dest_path}/{target_name}'

    os.makedirs(dest_module_path, exist_ok=True)

    for subdir, dirs, files in os.walk(origin_path):

        dirs[:] = [d for d in dirs if not has_end(d, ignored_dirs)]

        logging.info(f"subdir: {subdir} \ndirs: \n{dirs}")

        dir_name = subdir[subdir.rfind('/') + 1:]
        _new_dir = subdir.replace(origin_path, dest_module_path).replace(origin_name, target_name)

        logging.info(f'new dir: {_new_dir}')

        os.makedirs(_new_dir, exist_ok=True)

        for _file in files:

            if not has_end(_file, ignored_files):

                origin_file = os.path.join(subdir, _file)
                logging.info(f"origin:      {origin_file}")

                sep = os.sep
                # TODO add more insurances preventing bug where an incidental substring is replaced
                #  or one is accidentally excluded.
                destination_path = origin_file.replace(origin_path, dest_module_path)
                destination_path = destination_path.replace(f'{sep}{origin_name}{sep}', f'{sep}{target_name}{sep}')
                destination_path = destination_path.replace(f'{origin_name}-', f'{target_name}-')
                destination_path = destination_path.replace(f'{origin_name}_', f'{target_name}_')

                logging.info(f"destination: {destination_path}")

                if replace_in_copy:

                    variation_copy_file(
                        origin_path=origin_file,
                        dest_path=destination_path,
                        origin_name=origin_name,
                        target_name=target_name
                    )
                else:
                    copyfile(origin_file, destination_path)

                logging.debug('break')

            else:
                logging.info(f"ignoring dir_name: {dir_name}")

    return None


def variation_copy_file(origin_path, dest_path, origin_name, target_name):
    """

    :param origin_path:
    :param dest_path:
    :param origin_name:
    :param target_name:
    :return:
    """

    try:

        with open(origin_path, "rt") as file_in:

            with open(dest_path, "wt") as file_out:

                for line in file_in:

                    if origin_name in line:

                        line = line.replace(origin_name, target_name)

                    file_out.write(line)
    except Exception as e:

        logging.error(f'origin_path: {origin_path}')
        logging.error(e)


def create_app_shell_from_app(conf):

    plan = conf.app_shell_creation

    variation_copy_dir(
        origin_path=plan.source_root,
        dest_path=plan.dest_root,
        origin_name=plan.source_app,
        target_name=plan.app_name,
        ignored_dirs=plan.ignored_dirs,
        ignored_files=conf.ignored_files,
        replace_in_copy=True
    )

    variation_copy_dir(
        origin_path=plan.source_conf_root,
        dest_path=plan.dest_conf_root,
        origin_name=plan.source_app,
        target_name=plan.app_name,
        ignored_dirs=plan.ignored_dirs,
        ignored_files=conf.ignored_files,
        replace_in_copy=True
    )


def create_module_from_module(conf):

    plan = conf.module_creation

    variation_copy_dir(
        origin_path=plan.source_module_root,
        dest_path=plan.dest_module_root,
        origin_name=plan.source_module,
        target_name=plan.module_name,
        ignored_dirs=conf.ignored_dirs,
        ignored_files=conf.ignored_files,
        replace_in_copy=True
    )

    place_holder = f'{plan.dest_module_root}/stam.txt'

    with open(place_holder, "wt") as file_out:

        file_out.write('hamshif')

