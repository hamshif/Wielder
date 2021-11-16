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


def sync_filtered_to_kube(conf):

    stage = '/tmp/wield_dev_stage'

    os.makedirs(stage, exist_ok=True)
    shutil.rmtree(stage)
    os.makedirs(stage, exist_ok=True)

    for sync, sync_conf in conf.dev_sync.sync_dirs.items():

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


def sync_dev_to_kube(locale, conf):
    """
    Synchronises files (code & configuration) from a development workstation and kubernetes pods
    for development purposes

    # Example of config need to be add to developer.conf
    dev: {

        push: true
        dev_mode: false # if in dev mode then copy files to pod
        pod_names: [airflow-worker] # list of pods in which we need to push modules
        context: kind-pepticom-local

        airflow-worker {
               mount_folders: false # do we need mount pvc and classes to airflow-worker (custom parameter)
               module_list: [dud, pep-services, Wielder, pep-terraform]
               namespace: airflow
               pod_destination: /tmp/duds
          }
    }
    :param locale:
    :param conf:
    :return:
    """

    if conf.dev.push:

        for pod_search_name in conf.dev.pod_names:

            pod_settings = conf.dev[pod_search_name]
            pods = get_pods(pod_search_name, conf.kube_context, False, pod_settings.namespace)

            for module_name in pod_settings.module_list:
                copy_file_to_pods(
                    pods=pods,
                    src=f'{locale.super_project_root}/{module_name}',
                    pod_dest=f'{pod_settings.pod_destination}',
                    namespace=pod_settings.namespace,
                    context=conf.kube_context
                )
