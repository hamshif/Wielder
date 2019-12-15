#!/usr/bin/env python
import logging
import os
from shutil import copyfile

from wielder.util.arguer import get_create_parser
from wielder.util.log_util import setup_logging
from wielder.util.wgit import clone_or_update
from wielder.wield.enumerator import CodeLanguage

# TODO get these hardcoded constants from config
PROJECT_IGNORED_DIRS = ['__pycache__', 'personal', 'plan', 'artifacts', 'deploy', 'egg-info', 'datastores', '.git']
MODULE_IGNORED_DIRS = ['__pycache__', 'personal', 'plan', 'artifacts', 'egg-info', '.git']

IGNORED_FILE_TYPES = ['.iml', '.DS_Store', '.git', 'local.conf']

WIELD_SERVICES_SRC = 'https://github.com/hamshif/wield-services.git'

lang_module_map = {
    CodeLanguage.PYTHON: 'slate',
    CodeLanguage.PERL: 'pep',
    CodeLanguage.JAVA: 'boot',
}


def has_end(whole, ends):

    for end in ends:

        if whole.endswith(end):

            return True

    return False


def variation_copy_dir(origin_path, dest_path, origin_name, target_name, ignored_dirs=[],
                       ignored_files=[], replace_in_copy=True):
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

    os.makedirs(dest_path, exist_ok=True)

    for subdir, dirs, files in os.walk(origin_path):

        dirs[:] = [d for d in dirs if not has_end(d, ignored_dirs)]

        logging.info(f"subdir: {subdir} \ndirs: \n{dirs}")

        dir_name = subdir[subdir.rfind('/') + 1:]
        _new_dir = subdir.replace(origin_path, dest_path).replace(origin_name, target_name)

        logging.info(f'new dir: {_new_dir}')

        os.makedirs(_new_dir, exist_ok=True)

        for _file in files:

            if not has_end(_file, ignored_files):

                origin_file = os.path.join(subdir, _file)
                logging.info(f"origin:      {origin_file}")

                # TODO add more insurances preventing bug where an incidental substring is replaced
                #  or one is accidentally excluded.
                destination_path = origin_file.replace(origin_path, dest_path)
                destination_path = destination_path.replace(f'/{origin_name}/', f'/{target_name}/')
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


def create_infrastructure(create_wield_services, target_root, project_name,
                          target_module='micro', origin_module='slate'):

    wield_services_root = f'{target_root}/{project_name}/wield-services'

    origin_root = '/tmp/wield-services'

    clone_or_update(WIELD_SERVICES_SRC, origin_root, name=None, branch='master', local=False)

    standard_module_sub_path = '/src/wield_services/deploy'

    if create_wield_services:

        variation_copy_dir(
            origin_root,
            wield_services_root,
            origin_name=origin_module,
            target_name=target_module,
            ignored_dirs=PROJECT_IGNORED_DIRS,
            ignored_files=IGNORED_FILE_TYPES,
            replace_in_copy=False
        )

        modules_root = f'{wield_services_root}{standard_module_sub_path}'

    else:
        modules_root = f'{wield_services_root}'

    origin_path = f'{origin_root}{standard_module_sub_path}/{origin_module}'
    target_path = f'{modules_root}/{target_module}'

    variation_copy_dir(
        origin_path,
        target_path,
        origin_name=origin_module,
        target_name=target_module,
        ignored_dirs=MODULE_IGNORED_DIRS
    )


def create(create_args):

    container_lang = create_args.language

    # TODO map type and framework to origin [in config file]
    #  origin_module derived from CodeLanguage.PYTHON LanguageFramework.FLASK
    origin_module = lang_module_map.get(container_lang)

    create_infrastructure(
        create_wield_services=create_args.create_project,
        target_root=create_args.target_root,
        project_name=create_args.project_name,
        target_module=create_args.module_name,
        origin_module=origin_module
    )


def test():

    target_root = '/tmp/test/wielder-services'

    logging.info(f'testing project module creation in \n{target_root}')

    project_name = 'Dagdahuda'
    origin_module = 'pep'
    module_name = 'micro'

    create_infrastructure(
        create_wield_services=True,
        target_root=target_root,
        project_name=project_name,
        target_module=module_name,
        origin_module=origin_module
    )

    # create independent module
    create_infrastructure(
        create_wield_services=False,
        target_root=target_root,
        project_name=project_name,
        target_module=module_name,
        origin_module=origin_module
    )


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)
    create_parser = get_create_parser()
    _create_args = create_parser.parse_args()

    if _create_args.test:
        test()
    else:
        logging.info('creating module')
        create(_create_args)

