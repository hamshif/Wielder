#!/usr/bin/env python

__author__ = 'Gideon Bar'

import os

import logging

from wield_services.wield.deploy.imager import prepare_third_party_svc_image

from wielder.wield.enumerator import HelmCommand, KubeResType, WieldAction
from wielder.wield.kube_probe import observe_set, get_kube_res_by_name
from pyhocon.tool import HOCONConverter as Hc

from wielder.wield.wield_service import get_wield_svc


class WrapHelm:

    def __init__(self, conf, values_path=None,
                 res_type=KubeResType.STATEFUL_SET, res_name=None):

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

    def wield(self, helm_cmd=HelmCommand.INSTALL, observe=False):

        self.plan()

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

        try:
            data = get_kube_res_by_name(self.namespace, 'statefulset', self.release)
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
                os.system(f'kubectl create namespace {self.namespace}')
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
            os.system(f"kubectl -n {self.namespace} delete po -l app={self.res_name} --force --grace-period=0;")
            os.system(f"kubectl -n {self.namespace} delete pvc --all;")

        if observe:

            observe_set(self.namespace, self.res_type, self.res_name)

