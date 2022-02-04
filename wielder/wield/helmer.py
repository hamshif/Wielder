#!/usr/bin/env python

__author__ = 'Gideon Bar'

import os

import logging


from wielder.wield.enumerator import HelmCommand, KubeResType
from wielder.wield.kube_probe import observe_set, get_kube_res_by_name
from pyhocon.tool import HOCONConverter as Hc


class WrapHelm:

    def __init__(self, conf, values_path=None,
                 res_type=KubeResType.STATEFUL_SET):

        unique_name = conf.unique_name
        values_path = f'{values_path}/plan/{unique_name}'
        os.makedirs(values_path, exist_ok=True)

        self.unique_name = unique_name
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

        try:
            self.res_name = conf.res_name
        except Exception:
            self.res_name = self.release

        try:
            self.observe_timeout = conf.observe_timeout
        except Exception:
            self.observe_timeout = 400

        logging.debug('constructor finished')

    def plan(self):

        plan = Hc.convert(self.values, 'yaml', 2)

        logging.info(f'\n{plan}')

        with open(self.values_path, 'wt') as file_out:
            file_out.write(plan)

    def wield(self, helm_cmd=HelmCommand.INSTALL, observe=False, delete_pvc=True):

        self.plan()

        if helm_cmd == HelmCommand.NOTES:

            _cmd = f'helm --kube-context {self.context} get notes {self.release} -n {self.namespace}'
            logging.info(f'Running command:\n{_cmd}')

            try:
                os.system(_cmd)
            except:
                pass
            return
        elif helm_cmd == HelmCommand.INIT_REPO:
            _cmd = f'helm --kube-context {self.context} repo add {self.repo} {self.repo_url}'
            os.system(_cmd)
            logging.info(f'Running command:\n{_cmd}')
            os.system(_cmd)
            return

        try:
            data = get_kube_res_by_name(self.context, self.namespace, self.res_type, self.res_name)
        except:
            data = None

        if data is not None:
            if helm_cmd == HelmCommand.INSTALL:
                helm_cmd = HelmCommand.UPGRADE
        else:
            if helm_cmd == HelmCommand.UPGRADE:

                _cmd = f'helm repo update {self.repo}'

                os.system(_cmd)

                helm_cmd = HelmCommand.INSTALL

        _cmd = f'helm --kube-context {self.context} {helm_cmd.value} {self.release} -n {self.namespace}'

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

                pvc = get_kube_res_by_name(self.context, self.namespace, 'pvc', self.release)

                if pvc is not None:

                    pvc_name = pvc['metadata']['name']
                    _cmd = f"kubectl --context {self.context} -n {self.namespace} delete pvc {pvc_name};"
                    logging.info(f'Running cmd\n{_cmd}')
                    os.system(_cmd)

        if observe:

            self.observe()

    def observe(self):

        observe_set(self.context, self.namespace, self.res_type, self.res_name, self.observe_timeout)

