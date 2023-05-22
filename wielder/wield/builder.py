import logging
import os
import shutil
from abc import ABC, abstractmethod
from enum import Enum

from wielder.util.bucketeer import get_bucketeer
from wielder.util.util import DirContext
from wielder.util.wgit import WGit, clone_or_update
from wielder.wield.enumerator import RuntimeEnv, local_deployments


class BuilderType(Enum):
    MAVEN = 'Maven'


class WBuilder(ABC):

    def __init__(self, conf, locale):

        self.conf = conf
        self.locale = locale

        self.wg = WGit(locale.super_project_root)
        self.commit = self.wg.commit

        build_root = f'{locale.build_root}/{locale.super_project_name}'
        os.makedirs(build_root, exist_ok=True)
        self.build_root = build_root

        local_artifactory = f'{locale.local_buckets}/{conf.artifactory_bucket}'
        os.makedirs(local_artifactory, exist_ok=True)
        self.local_artifactory = local_artifactory

        self.artifactory = conf.artifactory_bucket
        self.bucketeer = get_bucketeer(conf, RuntimeEnv(conf.bootstrap_env), RuntimeEnv(conf.runtime_env))

    @abstractmethod
    def build_artifact(self, build_path):
        pass

    @abstractmethod
    def ensure_build_path(self, repo_name):
        pass

    @abstractmethod
    def ensure_artifact(self, repo_name, module_path, artifactory_key, push):
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

    def build_artifact(self, build_path):

        with DirContext(build_path):

            build_command = 'mvn clean install -U -f pom.xml'
            logging.info(f"Running cmd:\n{build_command}")
            os.system(build_command)
            # TODO make sense of the maven build and remove redundancies
            # build_command = 'mvn assembly:assembly -DdescriptorId=jar-with-dependencies'
            # logging.info(f"Running cmd:\n{build_command}")
            os.system(build_command)

    def ensure_build_path(self, repo_name):

        sub_commit = self.wg.get_submodule_commit(repo_name)

        submodule_path = 'kadlaomer'

        for sub_path in self.wg.get_submodule_names():

            if sub_path.endswith(repo_name):

                submodule_path = sub_path
                break

        source = f'{self.locale.super_project_root}/{submodule_path}'
        build_path = f'{self.build_root}/{submodule_path}'

        clone_or_update(
            source=source,
            destination=build_path,
            branch='dev',
            commit_sha=sub_commit
        )

        return sub_commit, build_path

    def ensure_artifact(self, repo_name, module_path, artifact_name, dependencies, artifactory_key='artifactory', push=True):
        """
        Lazily brings or builds an artifact corresponding to the exact super repo commit of the code.
        By default the artifact is pushed to the runtime environment bucket which serves as an artifactory.

        :param dependencies: Local build dependencies in case the artifact has to be built
        :param repo_name: The submodule where the artifact code resides
        :param module_path: The directory path to the module
        :param artifact_name:
        :param artifactory_key: the artifactory key e.g. spark/
        :param push: If the artifact should be pushed to the artifactory bucket or not, defaults to true
        :return:
        """

        full_local_artifactory_path = f'{self.local_artifactory}/{artifactory_key}'
        os.makedirs(full_local_artifactory_path, exist_ok=True)

        sub_commit, build_path = self.ensure_build_path(repo_name)

        local_artifact_path = f'{build_path}/{module_path}/target'.replace("//", '/')
        renamed = f'{artifact_name}-{sub_commit}.jar'

        full_local_path = f'{full_local_artifactory_path}/{renamed}'

        local_exists = self.verify_local_artifact(full_local_artifactory_path, renamed)

        if self.conf.runtime_env in local_deployments:

            if not local_exists:
                self.build_local_artifact(artifact_name, build_path, dependencies, full_local_path,
                                          local_artifact_path)
        else:

            remote_exists = self.verify_remote_artifact(artifactory_key, renamed)

            if remote_exists:

                if not local_exists:

                    self.bucketeer.cli_download_object(
                        bucket_name=self.artifactory,
                        key=f'{artifactory_key}/{renamed}',
                        dest=full_local_path
                    )
            else:

                if not local_exists:
                    self.build_local_artifact(artifact_name, build_path, dependencies, full_local_path,
                                              local_artifact_path)

                if push:
                    self.push_artifact(full_local_path, artifactory_key, renamed)

    def build_local_artifact(self, artifact_name, build_path, dependencies, full_local_path, local_artifact_path):

        for dependency in dependencies:
            _, dependency_repo_path = self.ensure_build_path(dependency.repo_name)
            dependency_path = f'{dependency_repo_path}/{dependency.module_path}'
            self.build_artifact(dependency_path)

        self.build_artifact(build_path)

        shutil.copyfile(f'{local_artifact_path}/{artifact_name}-1.0.0-SNAPSHOT-jar-with-dependencies.jar',
                        full_local_path)

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


def get_builder(conf, locale, builder_type):
    """
    Factory method for standardizing build access e.g. Maven, SBT, Gradle.
     depending on the combination of runtime environment and deploy environment.
    :param builder_type:
    :param locale:
    :param conf:
    :return:
    """

    builder = None

    if builder_type == BuilderType.MAVEN:
        builder = MavenBuilder(conf, locale)

    return builder
