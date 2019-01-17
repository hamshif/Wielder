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





