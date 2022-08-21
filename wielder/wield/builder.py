import logging
import os
import shutil
from abc import ABC, abstractmethod

from wielder.util.bucketeer import get_bucketeer
from wielder.util.util import DirContext
from wielder.util.wgit import WGit, clone_or_update
from wielder.wield.enumerator import RuntimeEnv


class WBuilder(ABC):

    def __init__(self, conf, locale):

        self.conf = conf
        self.locale = locale

        self.wg = WGit(locale.super_project_root)
        self.commit = self.wg.commit

        build_root = f'{locale.build_root}/{locale.super_project_name}'
        os.makedirs(build_root, exist_ok=True)

        self.build_root = build_root

        self.artifactory = conf.artifactory_bucket
        self.bucketeer = get_bucketeer(conf, RuntimeEnv(conf.bootstrap_env), RuntimeEnv(conf.runtime_env))

    @abstractmethod
    def build_artifact(self, repo_name, module_path, artifactory_key):
        pass

    @abstractmethod
    def verify_remote_artifact(self, artifact_key, artifact_name):
        pass

    @abstractmethod
    def verify_local_artifact(self, artifact_path, artifact_name):
        pass

    @abstractmethod
    def config_artifact(self):
        pass

    @abstractmethod
    def rename_artifact(self):
        pass

    @abstractmethod
    def push_artifact(self, local_path, artifactory_key, artifact_name):
        pass


class MavenBuilder(WBuilder):

    def __init__(self, conf, locale):

        super().__init__(conf, locale)

    def verify_remote_artifact(self, artifact_key, artifact_name):

        return self.bucketeer.object_exists(
            bucket_name=self.artifactory,
            prefix=artifact_key,
            object_name=artifact_name
        )

    def build_artifact(self, repo_name, module_path, artifactory_key='artifactory'):
        """

        :param repo_name:
        :param module_path:
        :param artifactory_key:
        :return:
        """

        sub_commit = self.wg.get_submodule_commit(repo_name)

        submodule_path = 'kadlaomer'

        for sub_path in self.wg.get_submodule_names():

            if sub_path.endswith(repo_name):

                submodule_path = sub_path
                break

        source = f'{self.locale.super_project_root}/{submodule_path}'
        build_dir = f'{self.build_root}/{submodule_path}'

        clone_or_update(
            source=source,
            destination=build_dir,
            branch='dev',
            commit_sha=sub_commit
        )

        artifact_name = module_path[module_path.rfind('/') + 1:]
        local_artifact_path = f'{build_dir}/{module_path}/target'
        renamed = f'{artifact_name}-{sub_commit}.jar'
        local_renamed = f'{local_artifact_path}/{renamed}'

        if not self.verify_local_artifact(local_artifact_path, renamed):

            if self.verify_remote_artifact(artifactory_key, renamed):

                self.bucketeer.cli_download_object(
                    bucket_name=self.artifactory,
                    key=f'{artifactory_key}/{renamed}',
                    dest=local_renamed
                )

            else:
                with DirContext(build_dir):

                    build_command = 'mvn clean install -f pom.xml'
                    logging.info(f"Running cmd:\n{build_command}")
                    os.system(build_command)

                shutil.copyfile(f'{local_artifact_path}/{artifact_name}-1.0.0-SNAPSHOT-jar-with-dependencies.jar', local_renamed)

        self.push_artifact(local_renamed, artifactory_key, renamed)

    def verify_local_artifact(self, artifact_path, artifact_name):

        exists = os.path.exists(f'{artifact_path}/{artifact_name}')

        return exists

    def config_artifact(self):
        pass

    def rename_artifact(self):
        pass

    def push_artifact(self, local_path, artifact_key, artifact_name):

        exists_in_artifactory = self.verify_remote_artifact(artifact_key, artifact_name)

        if not exists_in_artifactory:
            remote_name = f'{artifact_key}/{artifact_name}'
            self.bucketeer.cli_upload_file(local_path, self.artifactory, remote_name)


def get_builder(conf, locale, bootstrap_env=RuntimeEnv.MAC, runtime_env=RuntimeEnv.AWS):
    """
    Factory method for standardizing build access e.g. Maven, SBT, Gradle.
     depending on the combination of runtime environment and deploy environment.
    :param locale:
    :param conf:
    :param runtime_env: where this code is running
    :param bootstrap_env: where the code is built
    :return:
    """

    builder = MavenBuilder(conf, locale)

    return builder
