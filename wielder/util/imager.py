#!/usr/bin/env python
import logging
import os
from shutil import rmtree, copyfile, copytree
from wielder.util.commander import async_cmd
from wielder.util.log_util import setup_logging
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
        aws_push_image(cloud_conf, name, env, tag)


def aws_push_image(aws_conf, name, env, tag):

    region = aws_conf.image_repo_zone

    repo = f'{aws_conf.account_id}.dkr.ecr.{region}.amazonaws.com'

    cred = f'aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {repo}'

    os.system(cred)

    image_name = f'{repo}/{env}/{name}:{tag}'

    os.system(
        f'docker tag {name}:{env} {image_name};'
        f'docker push {image_name};'
    )

    logging.debug(f'aws ecr describe-images --repository-name  {env}/{name} --region {region};')


def pack_image(conf, name, image_root, push=False, force=False, tag='dev'):
    """

    :param tag:
    :param conf:
    :param name:
    :param push:
    :param force: force creation of image if it doesn't exist in repo
    :param image_root:
    :return:
    """

    dockerfile_dir = f'{image_root}/{name}'

    image_name = f'{name}'

    gcp_conf = conf.providers.gcp

    _cmd = f'docker images | grep {tag} | grep {image_name};'

    image_trace = async_cmd(
        _cmd
    )

    logging.info(f"{name} image_trace: {image_trace}")

    # Check if the list is empty
    if force or not image_trace:

        logging.info(f"attempting to create image {name}")

        os.system(
            f'docker build -t {image_name}:{tag} {dockerfile_dir};'
            f'echo "These are the resulting images:";'
            f'docker images | grep {tag} | grep {image_name};'
        )

    if push:
        gcp_push_image(gcp_conf)


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)
    logging.info('Poomba')
    logging.debug('Simba')
