import logging
import os
import shutil

from wielder.util.cool import filter_walk
from wielder.util.util import copy_file_to_pods
from wielder.wield.deployer import get_pods


def is_valid_file(name, forbidden):

    for f in forbidden:
        if name.endswith(f):
            return False

    return True


def is_valid_dir(name, forbidden):

    if name.endswith('.egg-info') or name[0] == '.' or name in forbidden:

        return False

    return True


def sync_filtered_to_kube(conf, module_name):
    """
    Synchronises select files (code & configuration) between local workstation and Kubernetes pods
    Files from a root directory are listed, filtering directories and files from configuration,
    into a tmp staging directory and then copied whole into pods (kubectl)

    :param conf: hocon configuration as in the example below.
    :param module_name
    :return:

    dev: {

      sync_list: []

      sync_dirs: {

        airflow_Wielder: {

          name: Wielder
          namespace: airflow
          pod_search_name: airflow-worker

          src: ${super_project_root}/Wielder
          dst: /data/${super_project_name}
        }
    }

    """
    stage = '/tmp/wield_dev_stage'

    os.makedirs(stage, exist_ok=True)
    shutil.rmtree(stage)
    os.makedirs(stage, exist_ok=True)

    dev_conf = conf[module_name].dev

    sync_list = dev_conf.sync_list

    for sync, sync_conf in dev_conf.sync_dirs.items():

        if sync in sync_list:

            sync_dir = sync_conf.name
            src = sync_conf.src

            fd = conf.ignored_dirs
            ff = conf.ignored_files

            gen = filter_walk(
                src,
                f_filter_dirs=is_valid_dir,
                forbidden_dirs=fd,
                f_filter_files=is_valid_file,
                forbidden_files=ff
            )

            nd = None

            for dir_path, sub_dirs, file_names in gen:

                nd = dir_path.replace(src, '')

                stage_dest = f'{stage}/{sync_dir}/{nd}'
                os.makedirs(stage_dest, exist_ok=True)

                for file_name in file_names:

                    src_file = f'{dir_path}/{file_name}'
                    tmp_file = f'{stage_dest}/{file_name}'

                    shutil.copyfile(src_file, tmp_file)

                print(f'dir_path: {nd}')
                print(f'sub_dir_names: {sub_dirs}')
                print(f'file_names: {file_names}')

            if nd is not None:

                pod_search_name = sync_conf.pod_search_name
                pods = get_pods(pod_search_name, conf.kube_context, False, sync_conf.namespace)

                src = f'{stage}/{sync_dir}'
                dst = sync_conf.dst

                copy_file_to_pods(
                    pods=pods,
                    src=src,
                    pod_dest=dst,
                    namespace=sync_conf.namespace,
                    context=conf.kube_context
                )
        else:
            logging.debug(f'{sync} wont be loaded')

