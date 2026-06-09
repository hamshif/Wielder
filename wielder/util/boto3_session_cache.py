import os

import boto3
import botocore.session
from botocore import credentials


def boto3_client(service_name, cred_locus='.aws/cli/cache'):
    """
    Create boto3 client from session
    Construct botocore session with cache
    By default the cache path is ~/.aws/boto/cache
    :param service_name: AWS service name e.g. 's3', 'ec2'
    :param cred_locus:
    :return:
    """

    cli_cache = os.path.join(os.path.expanduser('~'), cred_locus)
    session = botocore.session.get_session()
    session.get_component('credential_provider').get_provider('assume-role').cache = credentials.JSONFileCache(cli_cache)
    return boto3.Session(botocore_session=session).client(service_name)
