#!/usr/bin/env python
import logging
import os


import pyhocon


from wielder.util.bucketeer import AWSBucketeer
from wielder.util.util import parse_file, makedirs, copyfile
from wielder.wield.enumerator import local_deployments
from wielder.wield.project import configure_external_kafka_urls


def configure_remote_unique_context(conf, bucket_name=None):
    """
    Places project configuration in distributed env e.g. AWS
    Used for super cluster processes such as data pipelines.

    :param bucket_name: The bucket where the configuration exists
    :param conf: project level hocon conf
    :return:
    """

    if bucket_name is None:
        bucket_name = conf.namespace_bucket

    configure_external_kafka_urls(conf)

    unique_name = conf.unique_name

    app_plan_dir = f'{conf.project_conf_root}/plan'

    makedirs(app_plan_dir)
    # os.makedirs(app_plan_dir, exist_ok=True)

    unique_context_conf = f'{app_plan_dir}/{unique_name}.conf'

    with open(unique_context_conf, "w") as outfile:
        outfile.write(pyhocon.HOCONConverter.to_hocon(conf))

    artifactory_bucket = conf.artifactory_bucket

    unique_config_path = conf.unique_config_path
    logging.info(f'Configuring experiment {unique_name} at:\n{unique_config_path}')

    if conf.runtime_env in local_deployments:

        bucket_path = conf.local_buckets_root

        conf_path = f'{bucket_path}/{bucket_name}/{unique_config_path}'

        makedirs(conf_path)
        # os.makedirs(conf_path, exist_ok=True)

        copyfile(unique_context_conf, f'{conf_path}/{unique_name}.conf')
        # shutil.copyfile(unique_context_conf, f'{conf_path}/{unique_name}.conf')

    elif conf.runtime_env == 'aws':

        aws_zone = conf.aws_zone

        #  TODO this is broken for production fix bucket name issue
        b = AWSBucketeer(conf)

        bucket_names = b.get_bucket_names()

        if bucket_name not in bucket_names:
            b.create_bucket(bucket_name=bucket_name, region=aws_zone)

        if artifactory_bucket not in bucket_names:
            b.create_bucket(bucket_name=artifactory_bucket, region=aws_zone)

        names = b.get_object_names(bucket_name, unique_name)

        b.upload_file(
            unique_context_conf,
            bucket_name,
            f'{unique_config_path}/{unique_name}.conf'
        )

        names = b.get_object_names(bucket_name, unique_name)


def get_remote_unique_context(conf):
    namespace_bucket = conf.namespace_bucket
    unique_name = conf.unique_name
    unique_config_path = conf.unique_config_path

    bucket_path = conf.local_buckets_root

    conf_path = f'{bucket_path}/{namespace_bucket}/{unique_config_path}'
    file_name = f'{unique_name}.conf'

    if conf.runtime_env == 'aws':
        b = AWSBucketeer(conf)

        b.download_object(namespace_bucket, key=unique_config_path, name=file_name, dest=conf_path)

    # conf = ConfigFactory.parse_file(f'{conf_path}/{file_name}')
    conf = parse_file(conf_path, file_name)

    return conf


def download_stuff(conf):
    b = AWSBucketeer(conf)

    stuff = conf.stuff

    src_path = stuff.bucket_path
    bucket_name = stuff.bucket_name
    local_dest = stuff.local_dest

    os.system(f'atom {local_dest}')

    b.download_objects_by_key(
        bucket_name=bucket_name,
        root_key=src_path,
        dest=local_dest
    )


def sync_stuff(conf):
    b = AWSBucketeer(conf)

    sync_stuff = conf.sync_stuff

    source = sync_stuff.source
    dest = sync_stuff.dest

    src_path = sync_stuff.src_path
    dest_path = sync_stuff.dest_path

    for stuff in sync_stuff.stuffs:
        src_key = f'{src_path}/{stuff}'
        dest_key = f'{dest_path}/{stuff}'

        b.bucket_sync(
            source=source,
            dest=dest,
            src_prefix=src_key,
            dest_prefix=dest_key
        )


def upload_stuff(conf):
    b = AWSBucketeer(conf)

    stuff = conf.upload

    bucket_path = stuff.bucket_path
    bucket_name = stuff.bucket_name
    src = stuff.src

    b.upload_directory(src, bucket_name, bucket_path)
