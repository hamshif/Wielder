#!/usr/bin/env python

__author__ = 'Gideon Bar'

import logging
import os
import wielder.util.util as wu
import subprocess

from pyhocon.tool import HOCONConverter as Hc

from wielder.util.kuber import delete_pvcs, ensure_kubernetes_namespace
from wielder.wield.enumerator import HelmCommand, KubeResType
from wielder.wield.kube_probe import observe_set, get_kube_resources_by_name


class WrapHelm:

    def __init__(self, conf, values_path=None,
                 res_type=KubeResType.STATEFUL_SET):

        unique_name = conf.unique_name
        values_path = f'{values_path}/plan/{unique_name}'
        wu.makedirs(values_path, exist_ok=True)

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

    def _repo_exists(self) -> bool:
        proc = subprocess.run(
            ["helm", "repo", "list"],
            check=False,
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            if "no repositories to show" in (proc.stderr or "").lower():
                return False
            raise RuntimeError(
                "Failed listing Helm repositories.\n"
                f"stdout:\n{proc.stdout}\n"
                f"stderr:\n{proc.stderr}"
            )

        for line in proc.stdout.splitlines()[1:]:
            if line.strip().split():
                if line.strip().split()[0] == self.repo:
                    return True
        return False

    def _ensure_repo_initialized(self) -> None:
        if self._repo_exists():
            logging.info("Helm repo [%s] already exists. Skipping repo add.", self.repo)
            return

        repo_add_proc = subprocess.run(
            ["helm", "--kube-context", self.context, "repo", "add", self.repo, self.repo_url],
            check=False,
            text=True,
            capture_output=True,
        )
        if repo_add_proc.returncode != 0:
            raise RuntimeError(
                f"Failed adding Helm repo [{self.repo}] from [{self.repo_url}].\n"
                f"stdout:\n{repo_add_proc.stdout}\n"
                f"stderr:\n{repo_add_proc.stderr}"
            )

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
            self._ensure_repo_initialized()
            return

        data = get_kube_resources_by_name(self.context, self.namespace, self.res_type, self.res_name)

        if len(data) > 0:
            if helm_cmd == HelmCommand.INSTALL:
                helm_cmd = HelmCommand.UPGRADE
        else:
            if helm_cmd == HelmCommand.UNINSTALL:
                logging.info(
                    "Helm release [%s] resources are already absent in namespace [%s]. Skipping uninstall.",
                    self.release,
                    self.namespace,
                )
                if delete_pvc:
                    delete_pvcs(self.context, self.namespace, self.release)
                return
            if helm_cmd == HelmCommand.UPGRADE:

                _cmd = f'helm repo update {self.repo}'

                os.system(_cmd)

                helm_cmd = HelmCommand.INSTALL

        _cmd = f'helm --kube-context {self.context} {helm_cmd.value} {self.release} -n {self.namespace}'

        if helm_cmd == HelmCommand.INSTALL or helm_cmd == HelmCommand.UPGRADE:
            self._ensure_repo_initialized()

            ensure_kubernetes_namespace(self.context, self.namespace)

            _cmd = f'{_cmd} {self.chart}'

            if self.values_path is not None:

                _cmd = f'{_cmd} -f {self.values_path}'

            _cmd = f"{_cmd} --version {self.repo_version}"

        logging.info(f'Running command:\n{_cmd}')
        helm_proc = subprocess.run(_cmd, shell=True, check=False, text=True, capture_output=True)
        if helm_proc.returncode != 0:
            raise RuntimeError(
                f"Helm command failed with exit code {helm_proc.returncode}.\n"
                f"command:\n{_cmd}\n"
                f"stdout:\n{helm_proc.stdout}\n"
                f"stderr:\n{helm_proc.stderr}"
            )

        if helm_cmd == HelmCommand.UNINSTALL:
            observe = False
            subprocess.run(
                [
                    "kubectl",
                    "--context",
                    self.context,
                    "-n",
                    self.namespace,
                    "delete",
                    "po",
                    "-l",
                    f"app={self.res_name}",
                    "--force",
                    "--grace-period=0",
                ],
                check=False,
                text=True,
                capture_output=True,
            )

            if delete_pvc:

                delete_pvcs(self.context, self.namespace, self.release)

        if observe:

            self.observe()

    def observe(self):

        observe_set(self.context, self.namespace, self.res_type, self.res_name, self.observe_timeout)
