#!/usr/bin/env python

__author__ = 'Gideon Bar'

import os

import logging


from wielder.wield.enumerator import HelmCommand, KubeResType
from wielder.wield.kube_probe import observe_set, get_kube_res_by_name
from pyhocon.tool import HOCONConverter as Hc


class WrapHelm:

    def __init__(self, conf, values_path=None,
                 res_type=KubeResType.STATEFUL_SET, res_name=None):

        self.context = conf.kube_context
        self.repo = conf.repo
        self.repo_url = conf.repo_url
        self.namespace = conf.namespace
        self.release = conf.release
        self.conf = conf
        self.values = self.conf.helm_values
        self.repo_version = conf.repo_version
        self.chart = f'{self.repo}/{conf.chart}'
        self.values_path = f'{values_path}/{self.release}-values.yaml'
        self.res_type = res_type.value

        if res_name is None:
            res_name = self.release

        self.res_name = res_name

    def plan(self):

        plan = Hc.convert(self.values, 'yaml', 2)

        logging.info(f'\n{plan}')

        with open(self.values_path, 'wt') as file_out:
            file_out.write(plan)

    def wield(self, helm_cmd=HelmCommand.INSTALL, observe=False, observe_timeout=400, delete_pvc=True):

        self.plan()

        if helm_cmd == HelmCommand.NOTES:

            _cmd = f'helm --kube-context {self.context} get notes {self.release} -n {self.namespace}'
            logging.info(f'Running command:\n{_cmd}')
            os.system(_cmd)
            return
        elif helm_cmd == HelmCommand.INIT_REPO:
            _cmd = f'helm --kube-context {self.context} repo add {self.repo} {self.repo_url}'
            os.system(_cmd)
            logging.info(f'Running command:\n{_cmd}')
            os.system(_cmd)
            return

        try:
            data = get_kube_res_by_name(self.context, self.namespace, self.res_type, self.release)
        except:
            data = None

        if data is not None:
            if helm_cmd == HelmCommand.INSTALL:
                helm_cmd = HelmCommand.UPGRADE
        else:
            if helm_cmd == HelmCommand.UPGRADE:
                helm_cmd = HelmCommand.INSTALL

        _cmd = f'helm {helm_cmd.value} {self.release} -n {self.namespace}'

        if helm_cmd == HelmCommand.INSTALL or helm_cmd == HelmCommand.UPGRADE:

            try:
                os.system(f'kubectl --context {self.context} create namespace {self.namespace}')
            except:
                pass

            _cmd = f'{_cmd} {self.chart}'

            if self.values_path is not None:

                _cmd = f'{_cmd} -f {self.values_path}'

            _cmd = f"{_cmd} --version {self.repo_version}"

        logging.info(f'Running command:\n{_cmd}')
        os.system(_cmd)

        if helm_cmd == HelmCommand.UNINSTALL:
            observe = False
            os.system(f"kubectl --context {self.context} -n {self.namespace} delete po -l app={self.res_name} --force --grace-period=0;")

            if delete_pvc:
                os.system(f"kubectl --context {self.context} -n {self.namespace} delete pvc --all;")

        if observe:

            observe_set(self.context, self.namespace, self.res_type, self.res_name, observe_timeout)

