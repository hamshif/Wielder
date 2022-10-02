#!/usr/bin/env python
import os

from wielder.util.util import DirContext


def run_perl_script(conf, svc_name):

    svc_repo_path = conf.project_root
    perl_script_cmd = 'perl '

    build = conf.pack.build.build_instructions

    script_conf = build.services[svc_name]

    for lib in build.lib_dirs:

        perl_script_cmd = f'{perl_script_cmd} -I{svc_repo_path}/{lib}'

    perl_script_cmd = f'{perl_script_cmd} {svc_repo_path}/scripts/{script_conf.script}'

    for arg in script_conf.args:

        perl_script_cmd = f'{perl_script_cmd} {arg}'

    print(f'{svc_name} command:\n{perl_script_cmd}')

    with DirContext(svc_repo_path):

        os.system(f'{perl_script_cmd};')

    print("Balash")


