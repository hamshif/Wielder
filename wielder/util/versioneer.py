import logging
import os
from abc import ABC, abstractmethod

from wielder.util.credential_helper import get_aws_mfa_cred_command
from wielder.wield.enumerator import RuntimeEnv, local_deployments


class Versioneer(ABC):

    def __init__(self, conf):

        self.conf = conf

    @abstractmethod
    def create_repos(self):
        pass

    @abstractmethod
    def create_repo(self, svc_name):
        pass


class AWSVersioneer(Versioneer):

    def create_repo(self, svc_name):

        conf = self.conf

        repo_name = f'{conf.super_project_name}/{conf.deploy_env}/{svc_name}'

        ro = conf.aws_cred_role

        cmd_prefix = get_aws_mfa_cred_command(ro)

        _cmd = f'aws ecr create-repository --repository-name {repo_name} --region {conf.aws_zone}'

        _cmd = f'{cmd_prefix}{_cmd};'

        logging.info(f'running:\n{_cmd}')

        os.system(_cmd)

    def __init__(self, conf):

        super().__init__(conf)

    def create_repos(self):

        for svc_name in self.conf.repos:

            self.create_repo(svc_name)


class GithubVersioneer(Versioneer):

    def __init__(self, conf):

        super().__init__(conf)

    def create_repos(self):
        pass

    def create_repo(self, svc_name):
        pass


def get_versioneer(conf, repository_env=RuntimeEnv.AWS):

    if repository_env.value in local_deployments:
        pass
    elif repository_env == RuntimeEnv.AWS:
        return AWSVersioneer(conf)
