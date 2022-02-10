#!/usr/bin/env python
import logging
from datetime import datetime
from enum import Enum

import boto3
from botocore.exceptions import ClientError

from wielder.util.util import get_aws_session
from wielder.wield.enumerator import RuntimeEnv


class EMRClusterStatus(Enum):

    STARTING = 'STARTING'
    BOOTSTRAPPING = 'BOOTSTRAPPING'
    RUNNING = 'RUNNING'
    WAITING = 'WAITING'
    TERMINATING = 'TERMINATING'
    TERMINATED = 'TERMINATED'
    TERMINATED_WITH_ERRORS = 'TERMINATED_WITH_ERRORS'


def wrap_steps(conf, step_group):

    steps = []

    for step_name in conf[step_group].keys():
        step_conf = conf[step_group][step_name]

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
                    "-nb", conf.namespace_bucket,
                ]
            }
        }

        logging.info(f'step {step_name} in AWS format:\n{step}')

        steps.append(step)

    return steps


class Sparker:
    """
    This wrapper object was created mainly to retain the AMI session.
    We use MFA for development and the code is per process.
    It currently supports AWS S3, Later on we can add more Cloud providers
    """

    def __init__(self, conf, launch_env=RuntimeEnv.MAC):

        if launch_env == RuntimeEnv.AWS:
            session = boto3.Session(region_name=conf.aws_zone)
        else:
            session = get_aws_session(conf)

        self.emr = session.client('emr')

    def create_steps(self, pipeline_conf, f_wrap_steps=wrap_steps, step_group='jobs'):
        """Create EMR Steps in a specified region

        If a region is not specified, the bucket is created in the S3 default
        region (us-east-1).
        :param step_group: often spark jobs have different subgroups e.g kafka ingestion, purification ...
        :param f_wrap_steps: A function for extracting AWS from config e.g. wrap_steps above
        :param pipeline_conf: config for pipeline
        """
        try:

            steps = f_wrap_steps(pipeline_conf, step_group)

            response = self.emr.add_job_flow_steps(
                JobFlowId=pipeline_conf.cluster_id,
                Steps=steps
            )

            logging.info(f'response:\n{response}')

            return response

        except ClientError as e:
            logging.error(e)
            return False

    def get_cluster_id(self, cluster_regx, cluster_states=None, create_after=None):

        if create_after is None:
            create_after = datetime(2021, 6, 1)

        if cluster_states is None:
            cluster_states = [
                'STARTING', 'BOOTSTRAPPING', 'RUNNING', 'WAITING', 'TERMINATING', 'TERMINATED','TERMINATED_WITH_ERRORS'
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




