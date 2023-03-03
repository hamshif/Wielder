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
    An example"

    runtime_env: docker
    unique_name: huffelumph

    aws_profile: "pooh_bear"
    aws_cli_profile: "piglet"
    aws_user: christopher_robin
    ssh_password: "sanders"

    aws_account_id: "123456789"
    aws_zone: us-east-2
    aws_image_repo_zone: us-east-2

    namespace_bucket: owls_bucket

    pipelines: {

      runtime_env: ${runtime_env}
      namespace_bucket: ${namespace_bucket}
      unique_name = ${unique_name}

      cluster_id: j-227D24G662GL1

      kafka_ingestion: {
        KafkaModelIngestor {
          jar_path: "s3://"${namespace_bucket}"/spark/KafkaIngestion-1.0.0-SNAPSHOT.jar"
          main_class: "com.forest.christopher.pipelines.kafka_ingestion.KafkaModelIngestor"
       }

      KafkaDockingExperimentsIngestor {
          jar_path: "s3://"${namespace_bucket}"/spark/KafkaIngestion-1.0.0-SNAPSHOT.jar"
          main_class: "com.forest.christopher.pipelines.kafka_ingestion.KafkaDockingExperimentsIngestor"
      }
    }

    """

    def __init__(self, conf, launch_env=RuntimeEnv.MAC):

        super().__init__(conf, launch_env)

        if launch_env == RuntimeEnv.AWS:
            session = boto3.Session(region_name=conf.aws_zone)
        else:
            session = get_aws_session(conf)

        self.emr = session.client('emr')

        cluster_ids = self._get_cluster_id(cluster_regx=conf.unique_name, cluster_states=['RUNNING', 'WAITING'])

        if cluster_ids:
            cluster_id = cluster_ids[0]

            self.pipeline_conf.cluster_id = cluster_id

    def is_job_active(self, jobs_path=['jobs']):
        """Create EMR Steps in a specified region
        This relies on the pipelines configuration given in the constructor
        :param jobs_path: often spark jobs have different subgroups e.g kafka ingestion, purification ...
        """
        try:

            steps = self._wrap_steps(jobs_path)

            step_name = steps[0]['Name']

            response = self.emr.list_steps(
                ClusterId=self.pipeline_conf.cluster_id,
                StepStates=['PENDING', 'RUNNING'],
            )

            logging.info(f'response:\n{response}')

            for live_step in response['Steps']:
                if live_step['Name'] == step_name:
                    return True

            return False

        except ClientError as e:
            logging.error(e)
            return False

    def launch_jobs(self, jobs_path=['jobs']):
        """Create EMR Steps in a specified region
        This relies on the pipelines configuration given in the constructor
        :param jobs_path: often spark jobs have different subgroups e.g kafka ingestion, purification ...
        """
        try:

            steps = self._wrap_steps(jobs_path)

            # self.emr.

            response = self.emr.add_job_flow_steps(
                JobFlowId=self.pipeline_conf.cluster_id,
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
                    ClusterId=self.pipeline_conf.cluster_id,
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

        group = conf[step_group[0]]

        for key in step_group[1:]:
            group = group[key]

        for step_name in group.keys():
            step_conf = group[step_name]

            step = {
                'Name': step_name,
                'ActionOnFailure': 'CONTINUE',
                'HadoopJarStep': {
                    'Properties': [
                        {
                            'Key': 'string',
                            'Value': 'string'
                        },
                    ],
                    'Jar': 'command-runner.jar',
                    # 'MainClass': 'string',
                    'Args': [
                        "spark-submit",
                        "--class", step_conf.main_class,
                        "--deploy-mode", "client",
                        step_conf.jar_path,
                        "-re", conf.runtime_env,
                        "-u", conf.unique_name,
                        "-nb", conf.conf_bucket,
                    ]
                }
            }

            logging.info(f'step {step_name} in AWS format:\n{step}')

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

        for j in jobs_path:
            pc = pc[j]

        for job in pc.keys():
            job_conf = pc[job]

            _cmd = f"spark-submit --master spark://127.0.0.1:7077 " \
                   f"--class {job_conf.main_class} " \
                   f"{job_conf.local_jar_path} " \
                   f"-re local " \
                   f"-u {conf.unique_name} " \
                   f"-nb {conf.namespace_bucket} "

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
