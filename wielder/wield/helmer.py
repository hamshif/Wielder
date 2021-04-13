#!/usr/bin/env python

__author__ = 'Gideon Bar'

import os

import logging

from wielder.wield.enumerator import HelmCommand, KubeResType
from wielder.wield.kube_probe import observe_set


class WrapHelm:

    def __init__(self, repo, repo_url, chart, release, namespace='default', values_path=None,
                 res_type=KubeResType.STATEFUL_SET, res_name=None):

        self.repo = repo
        self.repo_url = repo_url
        self.chart = f'{repo}/{chart}'
        self.release = release
        self.namespace = namespace
        self.values_path = values_path
        self.res_type = res_type.value

        if res_name is None:
            res_name = release

        self.res_name = res_name

        os.system(f'kubectl create namespace {namespace}')

    def wield(self, helm_cmd=HelmCommand.INSTALL, observe=False):

        if helm_cmd == HelmCommand.NOTES:

            _cmd = f'helm get notes {self.release} -n {self.namespace}'
            logging.info(f'Running command:\n{_cmd}')
            os.system(_cmd)
            return
        elif helm_cmd == HelmCommand.INIT_REPO:
            _cmd = f'helm repo add {self.repo} {self.repo_url}'
            os.system(_cmd)
            logging.info(f'Running command:\n{_cmd}')
            os.system(_cmd)
            return

        _cmd = f'helm {helm_cmd.value} {self.release} -n {self.namespace}'

        if helm_cmd == HelmCommand.INSTALL or helm_cmd == HelmCommand.UPGRADE:

            _cmd = f'{_cmd} {self.chart}'

            if self.values_path is not None:

                _cmd = f'{_cmd} -f {self.values_path}'

        logging.info(f'Running command:\n{_cmd}')
        os.system(_cmd)

        if helm_cmd == HelmCommand.UNINSTALL:
            observe = False
            os.system(f"kubectl delete -n {self.namespace} po -l app={self.res_name} --force --grace-period=0;")

        if observe:
            observe_set(self.namespace, self.res_type, self.res_name)

