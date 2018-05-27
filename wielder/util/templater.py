#!/usr/bin/env python

import os

from wielder.util.arguer import get_kube_parser, process_args


# TODO Consider switching from tuples to dict
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
        # print(f"dirs: \n{dirs}")

        dir_name = subdir[subdir.rfind('/') + 1:]

        if dir_name not in conf.template_ignore_dirs:
            print(f"searching in dir_name: {dir_name}")

            for file in files:
                # print(f"file: {os.path.join(subdir, file)}")
                file_path = subdir + os.sep + file

                if file_path.endswith(".tmpl"):

                    template_files.append(file_path)
        else:
            print(f"ignoring dir_name: {dir_name}")

    return template_files


def remove_non_templates(dir_path, conf):
    """
    This function will delete files ending with .yaml .json from all sub  directories that are not ignored in conf
    :param dir_path: Path to the directory to be purged
    :return: None
    """

    for subdir, dirs, files in os.walk(dir_path):
        # print(f"dirs: \n{dirs}")

        dir_name = subdir[subdir.rfind('/') + 1:]

        if dir_name not in conf.template_ignore_dirs:
            print(f"searching in dir_name: {dir_name}")

            for file in files:
                # print(f"file: {os.path.join(subdir, file)}")
                full_path = subdir + os.sep + file

                if full_path.endswith(".yaml") or full_path.endswith(".json"):

                    os.remove(full_path)
        else:
            print(f"ignoring dir_name: {dir_name}")

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

                                    print(f"line: {line}     replacing {r[0]} with {r[1]}")
                                    file_out.write(line.replace(r[0], r[1]))
                                    break
                        else:
                            file_out.write(line)


if __name__ == "__main__":

    kube_parser = get_kube_parser()
    kube_args = kube_parser.parse_args()

    conf = process_args(kube_args)
    conf.attr_list(True)
    templates = gather_templates('/Users/gbar/stam/rtp/RtpKube/deploy/redis/test', conf)

    print(f"templates:\n{templates}")
    templates_to_instances(templates, conf.template_variables)


