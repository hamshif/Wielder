#!/usr/bin/env python
import logging
import os
from shutil import rmtree, copyfile, copytree
from wielder.util.commander import async_cmd
from wielder.util.log_util import setup_logging
from wielder.util.util import DirContext
from wielder.wield.enumerator import CloudProvider


def replace_file(origin_path, origin_regex, destination_path, final_name):
    """
    Validates existence of origin_regex
    Removes old destination
    Copies target with final_name to destination

    :param origin_path:
    :param origin_regex: Origin file regex e.g. App*.zip (AppV1.zip, AppV2.zip ...)
    :param destination_path:
    :param final_name:
    :return:
    """

    target_file = async_cmd(f"find {origin_path} -name {origin_regex}")[0][:-1]

    logging.info(f'Regex "{origin_regex}"" is fount in origin_path:  {target_file}')

    if target_file == '':

        logging.warning(f"couldn't find {origin_path}/{origin_regex} please run: ")
        return

    logging.info(f"Found {target_file} in target")

    full_destination = f"{destination_path}/{final_name}"

    try:
        os.remove(full_destination)

    except Exception as e:
        logging.error(str(e))

    copytree(target_file, full_destination)

    logging.info(f"successfully replaced {full_destination}")


def replace_dir_contents(origin_path, origin_regex, destination_path, destination_dir_name='artifacts'):
    """
    Used to update executable code for docker image packing
    e.g. interpreted code and artifacts.
    Validates existence of directory.
    Validates existence of a file regex in the directory for sanity purposes.
    Removes old destination.
    Copies directory contents to destination under artifacts directory

    :param origin_path: path to directory containing executables to be packed into image
    :param origin_regex: Origin file regex e.g. App*.zip (AppV1.zip, AppV2.zip ...)
           to be found in path for sanity check
    :param destination_path: A destination directory
           where the content of the executable directory can be copied to
    :param destination_dir_name: the name of the destination directory defaults to: artifacts
    :return:
    """

    target_file = async_cmd(f"find {origin_path} -name '{origin_regex}*'")[0][:-1]

    logging.info(
        f'Search results for regex <{origin_regex}> in origin_path:  {origin_path}:\n'
        f'{target_file}'
    )

    if target_file == '':

        logging.error(f"couldn't find {origin_path}/{origin_regex}\nPlease make sure it exists in path")
        return

    logging.info(f"Found {target_file} in target")

    full_destination = f"{destination_path}/{destination_dir_name}"

    rmtree(full_destination, ignore_errors=True)

    copytree(origin_path, full_destination)

    logging.info(f"successfully replaced {full_destination}")

    return target_file


def gcp_push_image(gcp_conf, name, env, tag):

    gcp_name = f'{gcp_conf.image_repo_zone}/{gcp_conf.project}/{env}/{name}'

    os.system(
        f'docker tag {name}:{tag} {gcp_name}:latest;'
        f'gcloud docker -- push {gcp_name}:latest;'
        f'gcloud container images list --repository={gcp_name};'
    )


def push_image(cloud_conf, name, env, tag, cloud=CloudProvider.GCP.value):

    if cloud == CloudProvider.GCP.value:
        gcp_push_image(cloud_conf, name, env, tag)
    elif cloud == CloudProvider.AWS.value:
        aws_push_image(cloud_conf, name, tag)


def aws_push_image(aws_conf, name, tag):

    region = aws_conf.image_repo_zone

    repo = f'{aws_conf.account_id}.dkr.ecr.{region}.amazonaws.com'

    profile = aws_conf.cred_profile

    cred = f'aws ecr --profile {profile} get-login-password --region {region} | docker login --username AWS ' \
           f'--password-stdin {repo} '

    logging.info(f'Running:\n{cred}')
    os.system(cred)

    image_name = f'{repo}/{name}:{tag}'

    _cmd = f'docker tag {name}:{tag} {image_name};'

    logging.info(f'Running cmd:\n')
    os.system(_cmd)

    _cmd = f'docker push {image_name};'

    logging.info(f'Running cmd:\n')
    os.system(_cmd)

    logging.info(f'aws ecr --profile {profile} describe-images --repository-name  {name} --region {region};')


def pack_image(image_root, name, image_name=None, force=False, tag='dev',
               runtime_env=None, kind_context='kind', build_args=None):
    """

    :param build_args: formulated arguments for docker build command e.g. tag=dev
    :param kind_context:
    :param runtime_env:
    :param image_name:
    :param tag:
    :param name: The name of the directory in which all the necessary resources for packing the image reside
    usually the name of the service.
    :param force: force creation of image if it doesn't exist in repo
    :param image_root:
    :return:
    """

    if image_name is None:
        image_name = name

    if build_args is None:
        build_args = ''
    else:
        build_args = f' --build-arg {build_args}'

    _cmd = f'docker images | grep {tag} | grep {image_name};'

    image_trace = async_cmd(
        _cmd
    )

    logging.info(f"{name} image_trace: {image_trace}")

    # Check if the list is empty
    if force or not image_trace:

        logging.info(f"attempting to create image {name}")

        _cmd = f'docker build -t {image_name}:{tag}{build_args} {image_root};'

        logging.info(f'running:\n{_cmd}')

        os.system(_cmd)

        _cmd = f'docker images | grep {tag} | grep {image_name};'

        logging.info(f'running:\n{_cmd}')

        os.system(_cmd)

        if runtime_env is not None and runtime_env == 'kind':

            _cmd = f'kind load docker-image {image_name}:{tag} --name {kind_context}'

            logging.info(f'running:\n{_cmd}')

            os.system(_cmd)


def shallow(base, tag, host_path, host_target, image_dest):
    """
    Use with caution!!!
    This function builds another layer on an existing image.
    The base looks like this:
        ARG BASE
        ARG TAG
        ARG HOST_PATH
        ARG IMAGE_PATH

        FROM ${BASE}:${TAG}
        COPY ${TARGET} ${IMAGE_PATH}

    Intended use case is to change configuration on an existing image

    :param host_target: The file or directory to be added to the image
    :param base: image name
    :param tag: image tag
    :param host_path:
    :param image_dest:
    :return:
    """

    _cmd = f'docker build . -t {base}:{tag} ' \
           f'--build-arg BASE={base} ' \
           f'--build-arg TAG={tag} ' \
           f'--build-arg HOST_TARGET={host_target} ' \
           f'--build-arg IMAGE_DEST={image_dest} '

    logging.info(f'running command:\n{_cmd}')

    here = __file__
    i = here.rfind('/')
    here = here[:i]
    _shallow = f'{here}/shallow'

    logging.debug(f'shallow is:\n{_shallow}')

    copyfile(f'{_shallow}/Dockerfile',  f'{host_path}/Dockerfile')

    with DirContext(host_path):

        os.system('ls -la')
        os.system(_cmd)


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)
    logging.info('Poomba')
    logging.debug('Simba')
