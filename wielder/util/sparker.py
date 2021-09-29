#!/usr/bin/env python
import logging

import boto3
from botocore.exceptions import ClientError

from wielder.util.util import get_aws_session


def wrap_steps(conf):

    steps = []

    for step_name in conf.jobs.keys():
        step_conf = conf.jobs[step_name]

        step = {
            'Name': step_conf.name,
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

    def __init__(self, conf=None):

        if conf is None:
            session = boto3.Session()
        else:
            session = get_aws_session(conf)

        self.emr = session.client('emr')

    def create_steps(self, conf, f_wrap_steps=wrap_steps):
        """Create EMR Steps in a specified region

        If a region is not specified, the bucket is created in the S3 default
        region (us-east-1).
        :param f_wrap_steps: A function for extracting AWS from config e.g. wrap_steps above
        :param conf: config for pipeline
        """
        try:

            steps = f_wrap_steps(conf)

            response = self.emr.add_job_flow_steps(
                JobFlowId=conf.cluster_id,
                Steps=steps
            )

            logging.info(f'response:\n{response}')

            return response

        except ClientError as e:
            logging.error(e)
            return False







