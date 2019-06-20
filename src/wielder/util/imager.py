#!/usr/bin/env python
import os
from shutil import copyfile
from wielder.util.commander import async_cmd


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

    print(f"zip is: {target_file}")

    if target_file == '':

        print(f"couldn't find {origin_path}/{origin_regex} please run: ")
        return

    print(f"Found {target_file} in target")

    full_destination = f"{destination_path}/{final_name}"

    try:
        os.remove(full_destination)

    except Exception as e:
        print(str(e))

    copyfile(target_file, full_destination)

    print(f"successfully replaced {full_destination}")


# TODO untested
def push_image(gcp_conf, name):

    # TODO repo as args
    os.system(
        f'gcloud docker -- push {gcp_conf.image_repo_zone}/{gcp_conf.project}/{name}:latest;'
        f'gcloud container images list --repository={gcp_conf.image_repo_zone}/{gcp_conf.project}/rtp/{name};'
    )


def pack_image(conf, name, image_root, push=False, force=False, tag='dev', mount=False, code_path=None):
    """

    :param tag:
    :param mount: if mount from local directory is to occur
    :param code_path: Path to code which should be mounted to docker for local dev
    :param conf:
    :param name:
    :param push:
    :param force: force creation of image if it doesn't exist in repo
    :param image_root:
    :return:
    """

    dockerfile_dir = f'{image_root}/{name}'

    image_name = f'{name}'

    if mount:

        dockerfile_dir = f'{dockerfile_dir}-mount'
        image_name = f'{name}/mount'

    gcp_conf = conf.providers.gcp

    image_trace = async_cmd(
        f'$(docker images | grep {name} | grep base);'
    )

    print(f"{name} image_trace: {image_trace}")

    # Check if the list is empty
    if force or not image_trace:

        print(f"attempting to create image {name}")

        # TODO add an error report and exit after failure in base
        os.system(
            f'docker build -t {image_name}:{tag} {dockerfile_dir};'
            # f'docker tag {name}:dev {gcp_conf.image_repo_zone}/{gcp_conf.project}/{name}:latest;'
            f'echo "These are the resulting images:";'
            f'docker images | grep {name};'
        )

    if push:
        push_image(gcp_conf)




