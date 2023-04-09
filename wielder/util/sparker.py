#!/usr/bin/env python
import logging
import os
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod
from time import sleep

import boto3
from botocore.exceptions import ClientError

from wielder.util.util import get_aws_session, DirContext
from wielder.wield.enumerator import RuntimeEnv


class SparkRuntime(Enum):
    EMR = 'emr'
    DATAPROC = 'dataproc'
    DATABRICKS = 'databricks'
    DEV_SERVER = 'unix'


class Sparker(ABC):

    def __init__(self, conf, launch_env=RuntimeEnv.MAC):

        self.conf = conf
        self.launch_env = launch_env
        self.pipeline_conf = conf.pipelines

    @abstractmethod
    def launch_jobs(self, jobs='jobs'):
        pass

    @abstractmethod
    def is_job_active(self, jobs_path=['jobs']):
        pass


class EMRClusterStatus(Enum):

    STARTING = 'STARTING'
    BOOTSTRAPPING = 'BOOTSTRAPPING'
    RUNNING = 'RUNNING'
    WAITING = 'WAITING'
    TERMINATING = 'TERMINATING'
    TERMINATED = 'TERMINATED'
    TERMINATED_WITH_ERRORS = 'TERMINATED_WITH_ERRORS'


class EMRSparker(Sparker):
    """
    This wrapper object was created to automate steps creation on AWS EMR.
    It retains the AMI session. We use MFA for bootstrapping development.
    """

    def __init__(self, conf, launch_env=RuntimeEnv.MAC):

        super().__init__(conf, launch_env)

        if launch_env == RuntimeEnv.AWS:
            session = boto3.Session(region_name=conf.aws_zone)
        else:
            session = get_aws_session(conf)

        self.emr = session.client('emr')
        self.cluster_id = self.pipeline_conf.cluster_id

        cluster_ids = self._get_cluster_id(cluster_regx=conf.emr_regex, cluster_states=['RUNNING', 'WAITING'])

        if cluster_ids:
            cluster_id = cluster_ids[0]

            self.cluster_id = cluster_id

    def is_job_active(self, jobs_path='jobs'):
        """
        Return True if any of the EMR steps are running
        This relies on the pipelines configuration given in the constructor
        :param jobs_path: often spark jobs have different subgroups e.g kafka ingestion, purification ...
        """
        try:

            steps = self._wrap_steps(jobs_path)

            response = self.emr.list_steps(
                ClusterId=self.cluster_id,
                StepStates=['PENDING', 'RUNNING'],
            )

            for step in steps:

                step_name = step['Name']

                logging.info(f'response:\n{response}')

                for live_step in response['Steps']:
                    if live_step['Name'] == step_name:
                        return True

            return False

        except ClientError as e:
            logging.error(e)
            return False

    def launch_jobs(self, jobs_path='jobs'):
        """Create EMR Steps in a specified region
        This relies on the pipelines configuration given in the constructor
        :param jobs_path: often spark jobs have different subgroups e.g kafka ingestion, purification ...
        """
        try:

            steps = self._wrap_steps(jobs_path)

            # self.emr.

            response = self.emr.add_job_flow_steps(
                JobFlowId=self.cluster_id,
                Steps=steps
            )

            logging.info(f'response:\n{response}')

            return response

        except ClientError as e:
            logging.error(e)
            return False

    def block_for_jobs_completion(self, step_ids, max_wait=50, interval=10):

        complete = True

        for i in range(max_wait):

            for step_id in step_ids:

                response = self.emr.describe_step(
                    ClusterId=self.cluster_id,
                    StepId=step_id
                )

                status = response['Step']['Status']['State']

                if status in ['CANCELLED', 'FAILED', 'CANCEL_PENDING', 'INTERRUPTED']:
                    logging.error(f'EMR step failed:\n{response}')
                    return False
                else:
                    logging.info(f'EMR step status:\n{response}')

                    if status == 'COMPLETED':
                        continue
                    else:
                        complete = False

            if complete:
                return True
            else:
                complete = True

                if i + 1 < max_wait:
                    logging.info(f'Sleeping {interval} to see if steps completed.')
                    sleep(interval)

        return complete

    def _get_cluster_id(self, cluster_regx, cluster_states=None, create_after=None):

        if create_after is None:
            create_after = datetime(2021, 6, 1)

        if cluster_states is None:
            cluster_states = [
                'STARTING', 'BOOTSTRAPPING', 'RUNNING', 'WAITING', 'TERMINATING', 'TERMINATED', 'TERMINATED_WITH_ERRORS'
            ]

        clusters = self.emr.list_clusters(
            CreatedAfter=create_after,
            # CreatedBefore=datetime(2021, 6, 1),
            ClusterStates=cluster_states,
            # Marker='something about the cluster'
        )['Clusters']

        cluster_ids = []

        for cluster in clusters:

            name = cluster['Name']

            logging.debug(f'cluster name: {name}')

            if cluster_regx in name:

                cluster_id = cluster['Id']
                logging.debug(f'cluster id: {cluster_id}')
                cluster_ids.append(cluster_id)

        print('ashmagog')
        return cluster_ids

    def _wrap_steps(self, step_group):

        steps = []

        conf = self.pipeline_conf

        group = conf[step_group]

        for step_conf in group:

            act = step_conf.ActionOnFailure if 'ActionOnFailure' in step_conf else 'CONTINUE'
            config_bucket = step_conf.config_bucket if 'config_bucket' in step_conf else conf.namespace_bucket

            inner_args = [
                "spark-submit",
                "--class", step_conf.main_class,
                "--deploy-mode", "client",
                step_conf.jar_path,
                "-re", conf.runtime_env,
                "-u", conf.unique_name,
                "-nb", config_bucket,
            ]

            if 'app' in step_conf:

                inner_args.append('-ap')
                inner_args.append(step_conf.app)

            step = {
                'Name': step_conf.Name,
                'ActionOnFailure': act,
                'HadoopJarStep': {
                    'Properties': [
                        {
                            'Key': 'string',
                            'Value': 'string'
                        },
                    ],
                    'Jar': 'command-runner.jar',
                    # 'MainClass': 'string',
                    'Args': inner_args
                }
            }


            logging.info(f'step {step_conf.Name} in AWS format:\n{step}')

            steps.append(step)

        return steps


class DevSparker(Sparker):
    """
    This wrapper object was created mainly to retain the AMI session.
    We use MFA for development and the code is per process.
    It currently supports AWS S3, Later on we can add more Cloud providers
    """

    def is_job_active(self, jobs_path=['jobs']):

        return False
        # raise Exception("is_job_active function must be implemented in DevSparker class")

    def __init__(self, conf, launch_env=RuntimeEnv.MAC):

        super().__init__(conf, launch_env)

    def launch_jobs(self, jobs_path='jobs'):
        """
        Create Local Spark jobs
        :param jobs_path: often spark jobs have different subgroups e.g kafka ingestion, purification ...
        """

        conf = self.conf
        pc = self.pipeline_conf

        jobs_conf = pc[jobs_path]

        for job_conf in jobs_conf:

            _cmd = f"spark-submit --master spark://127.0.0.1:7077 " \
                   f"--class {job_conf.main_class} " \
                   f"{job_conf.jar_path} " \
                   f"-re local " \
                   f"-u {conf.unique_name} " \
                   f"-nb {job_conf.config_bucket} " \

            if 'app' in job_conf:

                _cmd = _cmd + f'-ap {job_conf.app}'


            logging.info(f'running command:\n{_cmd}')

            with DirContext(conf.super_project_root):
                os.system(_cmd)


def get_sparker(conf, launch_env=RuntimeEnv.MAC, spark_runtime_env=SparkRuntime.EMR):
    """
    Factory method for getting different spark job launchers depending on the runtime environment
    :param conf:
    :param launch_env: where this code is running
    :param spark_runtime_env: where spark is expected to run
    :return:
    """

    if spark_runtime_env == SparkRuntime.EMR:

        return EMRSparker(conf, launch_env=launch_env)

    elif spark_runtime_env == SparkRuntime.DEV_SERVER:

        return DevSparker(conf, launch_env=launch_env)

    raise ValueError(spark_runtime_env)
