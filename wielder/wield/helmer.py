#!/usr/bin/env python

__author__ = 'Gideon Bar'

import os

import logging

from wield_services.wield.deploy.configurer import get_project_deploy_mode

from wielder.wield.enumerator import HelmCommand, KubeResType, WieldAction
from wielder.wield.kube_probe import observe_set, get_kube_res_by_name
from pyhocon.tool import HOCONConverter as Hc

from wielder.wield.wield_service import get_wield_svc


class WrapHelm:

    def __init__(self, conf, repo, repo_version, repo_url, chart, release, namespace='default', values_path=None,
                 res_type=KubeResType.STATEFUL_SET, res_name=None):

        self.conf = conf
        self.repo = repo
        self.repo_url = repo_url
        self.repo_version = repo_version
        self.chart = f'{repo}/{chart}'
        self.release = release
        self.namespace = namespace
        self.values_path = f'{values_path}/{release}-values.yaml'
        self.res_type = res_type.value

        if res_name is None:
            res_name = release

        self.res_name = res_name

    def plan(self):

        plan = Hc.convert(self.conf, 'yaml', 2)

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
            os.system(f"kubectl delete -n {self.namespace} po -l app={self.res_name} --force --grace-period=0;")

        if observe:

            observe_set(self.namespace, self.res_type, self.res_name)


def get_helm_wrap(conf_key, locale, res_type=KubeResType.STATEFUL_SET, action=None, has_service=False, auto_approve=False, service_only=False):
    """
    Helper method for extracting helm wrapper variables from configuration
    :param res_type: kubernetes resource type to track
    :param conf: Hocon config object
    :param conf_key: Key for specific helm configuration
    :param locale: helps locate where the values file exists
    :return:
    """

    if has_service:

        _action, service = get_wield_svc(locale, 'airflow')

        conf = service.conf

        if action is None:
            action = _action

        service.plan.wield(
            action=action,
            auto_approve=auto_approve,
            service_only=service_only
        )

    else:

        wield_mode, conf, _action = get_project_deploy_mode()
        _observe = True if _action == WieldAction.APPLY else False

    context_conf = conf.third_party.helm[conf_key]
    repo = context_conf.repo
    repo_url = context_conf.repo_url
    chart = context_conf.chart
    namespace = context_conf.namespace
    release = context_conf.release

    deploy_path = f'{locale.module_root}'
    os.system(f'ls -la {deploy_path}')

    wh = WrapHelm(
        conf=conf,
        repo=repo,
        repo_version=context_conf.repo_version,
        repo_url=repo_url,
        chart=chart,
        release=release,
        namespace=namespace,
        values_path=deploy_path,
        res_type=res_type
    )

    return wh
