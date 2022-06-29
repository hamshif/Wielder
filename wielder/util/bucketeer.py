#!/usr/bin/env python
import logging
import os
import pathlib
import shutil
from abc import ABC, abstractmethod

from botocore.exceptions import ClientError

from wielder.util.boto3_session_cache import boto3_client
from wielder.util.util import get_aws_session
from wielder.wield.enumerator import RuntimeEnv, local_deployments
from wielder.wield.project import WielderProject

DEFAULT_REGION = "us-east-2"


class Bucketeer(ABC):

    def __init__(self, conf):

        self.conf = conf

    @abstractmethod
    def create_bucket(self, bucket_name, region=None):
        pass

    @abstractmethod
    def upload_file(self, source, bucket_name, dest):
        pass

    @abstractmethod
    def upload_directory(self, source, bucket_name, prefix):
        pass

    @abstractmethod
    def download_object(self, bucket_name, key, name, dest='/tmp'):
        pass

    @abstractmethod
    def download_objects(self, bucket_name, root_key='', dest='/tmp'):
        pass

    @abstractmethod
    def delete_file(self, bucket_name, file_name):
        pass

    @abstractmethod
    def delete_bucket(self, bucket_name):
        pass

    @abstractmethod
    def get_bucket_names(self):
        pass

    @abstractmethod
    def get_object_names(self, bucket_name, prefix=''):
        pass


class AWSBucketeer(Bucketeer):
    """
    A convenience interface for working with AWS buckets.
    This wrapper object was created mainly to retain the AMI session.
    We use MFA for development and the code is per process.
    It currently supports AWS S3.
    """

    def __init__(self, conf=None):

        super().__init__(conf)

        if conf is None:
            logging.info('conf is None getting default client')
            self.s3 = boto3_client(service_name='s3')
        else:

            session = get_aws_session(conf)

            self.s3 = session.resource('s3').meta.client

    def create_bucket(self, bucket_name, region=None):
        """Create an S3 bucket in a specified region

        If a region is not specified, the bucket is created in the S3 default
        region (us-east-1).

        :param bucket_name: Bucket to create
        :param region: String region to create bucket in, e.g., 'us-east-2'
        :return: True if bucket created, else False
        """
        try:
            if region is None:
                region = DEFAULT_REGION

            location = {'LocationConstraint': region}
            response = self.s3.create_bucket(Bucket=bucket_name,
                                             CreateBucketConfiguration=location)
            print(response)
        except ClientError as e:
            logging.error(e)
            return False
        return True

    def upload_file(self, source, bucket_name, dest):

        with open(source, "rb") as f:
            self.s3.upload_fileobj(f, bucket_name, dest)

    def upload_directory(self, source, bucket_name, prefix):

        for root, dirs, files in os.walk(source):
            for file in files:

                sub = root.replace(source, '')

                if sub == '/':
                    sub = ''
                else:
                    sub = f'{sub}/'

                dest = f'{prefix}{sub}{file}'
                print(dest)
                self.s3.upload_file(os.path.join(root, file), bucket_name, dest)

    def download_object(self, bucket_name, key, name, dest='/tmp'):
        """
        Download a chunk of objects

        :param key:
        :param name: the object's full key
        :param dest: local destination prefix
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        try:

            print(name)

            # create nested directory structure
            os.makedirs(dest, exist_ok=True)

            # save file with full path locally
            self.s3.download_file(bucket_name, f'{key}/{name}', f'{dest}/{name}')

        except ClientError as e:
            logging.error(e)
            return False
        return True

    def download_objects(self, bucket_name, root_key='', dest='/tmp'):
        """
        Download a chunk of objects

        :param dest: local destination prefix
        :param root_key:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """

        try:

            names = self.get_object_names(bucket_name, root_key)

            for name in names:

                obj_path = name[:name.rindex('/')]

                obj_name = name.split('/')[-1]
                logging.debug(f'obj_path: {obj_path}\nobj_name: {obj_name}')

                ok = self.download_object(bucket_name, obj_path, obj_name, dest)
                if not ok:
                    return False

        except ClientError as e:
            logging.error(e)
            return False

        return True

    def delete_file(self, bucket_name, file_name):
        """Delete an S3 object
        :param file_name:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        try:

            self.s3.delete_object(
                Bucket=bucket_name,
                Key=file_name
            )

        except ClientError as e:
            logging.error(e)
            return False
        return True

    def delete_objects(self, bucket_name, prefix=''):
        """Empty an S3 bucket

        :param prefix:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        try:

            names = self.get_object_names(bucket_name, prefix)

            obs = [{'Key': n} for n in names]

            self.s3.delete_objects(
                Bucket=bucket_name,
                Delete={
                    'Objects': obs
                }
            )

        except ClientError as e:
            logging.error(e)
            return False
        return True

    def delete_bucket(self, bucket_name):
        """Delete an S3 bucket by emptying it and deleting the empty bucket.

        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        try:

            self.delete_objects(bucket_name)
            self.s3.delete_bucket(Bucket=bucket_name)

        except ClientError as e:
            logging.error(e)
            return False
        return True

    def get_bucket_names(self):
        """
        Retrieve a list of existing buckets.
        :return: list of bucket names
        """

        bucket_names = []

        response = self.s3.list_buckets()

        # Output the bucket names
        print('Existing buckets:')
        for bucket in response['Buckets']:
            bucket_names.append(bucket["Name"])
            print(f'  {bucket["Name"]}')

        return bucket_names

    def get_object_names(self, bucket_name, prefix=''):

        try:
            response = self.s3.list_objects(Bucket=bucket_name, Prefix=prefix)

            object_names = []

            if 'Contents' in response:
                s3objects = response['Contents']
                for obj in s3objects:
                    object_name = obj["Key"]
                    logging.debug(f'Object name: {object_name}')
                    object_names.append(object_name)

            return object_names

        except KeyError as e:
            logging.error(e)
            logging.info(f"No objects in key {prefix}")


class DevBucketeer(Bucketeer):
    """
    A mock bucket object
    The class emulates a cloud bucket by performing similar functionality on
    A directory
    """

    def __init__(self, conf=None):

        super().__init__(conf)

        wpj = WielderProject()

        self.buckets_root = wpj.mock_buckets_root
        self.default_bucket = conf.namespace_bucket

    def create_bucket(self, bucket_name, region=None):
        """Create a local directory to emulate cloud bucket behavior

        :param bucket_name: Bucket to create
        :param region: Ignored but kept to save interface compatibility
        :return: True if bucket created, else False
        """
        os.makedirs(f'{self.buckets_root}/{bucket_name}', exist_ok=True)

        return True

    def upload_file(self, source, bucket_name, dest):

        shutil.copy(source, f'{self.buckets_root}/{bucket_name}/{dest}')

    def upload_directory(self, source, bucket_name, prefix):

        shutil.copytree(source, f'{self.buckets_root}/{bucket_name}/{prefix}')

    def download_object(self, bucket_name, key, name, dest='/tmp'):
        """
        Pretend to download a file by copying

        :param key: the object's full path
        :param name: the object's last key
        :param dest: local destination prefix
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        try:

            print(name)

            # create nested directory structure
            os.makedirs(dest, exist_ok=True)
            src = f'{self.buckets_root}/{bucket_name}/{key}/{name}'

            stale = f'{dest}/{name}'
            if os.path.isfile(stale):
                os.remove(stale)

            shutil.copy(src, dest)

        except ClientError as e:
            logging.error(e)
            return False
        return True

    def download_objects(self, bucket_name, root_key='', dest='/tmp'):
        """
        Copies A directory emulating download of a chunk of objects from cloud bucket

        :param dest: local destination prefix
        :param root_key:
        :param bucket_name: Bucket
        :return: True
        """
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(f'{self.buckets_root}/{bucket_name}/{root_key}', dest)

        return True

    def delete_file(self, bucket_name, file_name):
        """Delete a file to emulate deleting a bucket object
        :param file_name:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """

        shutil.rmtree(f'{self.buckets_root}/{bucket_name}/{file_name}', ignore_errors=True)

        return True

    def delete_objects(self, bucket_name, prefix=''):
        """Empty a local Dir emulating a bucket

        :param prefix:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        shutil.rmtree(f'{self.buckets_root}/{bucket_name}/{prefix}', ignore_errors=True)

        return True

    def delete_bucket(self, bucket_name):
        """Delete an S3 bucket by emptying it and deleting the empty bucket.

        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """

        shutil.rmtree(f'{self.buckets_root}/{bucket_name}', ignore_errors=True)

        return True

    def get_bucket_names(self):
        """
        Retrieve a list of existing buckets.
        :return: list of bucket names
        """

        bucket_names = [p for p in pathlib.Path(f'{self.buckets_root}').iterdir() if p.is_dir()]

        return bucket_names

    def get_object_names(self, bucket_name, prefix=''):

        try:

            bucket_names = [p for p in pathlib.Path(f'{self.buckets_root}/{prefix}').iterdir() if p.is_dir()]

            return bucket_names

        except KeyError as e:
            logging.error(e)
            logging.info(f"No objects in key {prefix}")


def get_bucketeer(conf, bootstrap_env=RuntimeEnv.MAC, runtime_env=RuntimeEnv.AWS):
    """
    Factory method for standardizing bucket access e.g. S3 boto3 client, GCP Client , Local Directory to simulate bucket,
     depending on the combination of runtime environment and deploy environment.
    :param conf:
    :param runtime_env: where this code is running
    :param bootstrap_env: where spark is expected to run
    :return:
    """

    if bootstrap_env.value in local_deployments:

        if runtime_env == RuntimeEnv.AWS:
            return AWSBucketeer(conf)
        elif runtime_env == RuntimeEnv.DOCKER or runtime_env == RuntimeEnv.KIND:
            return DevBucketeer(conf)

    elif bootstrap_env == RuntimeEnv.AWS:
        return AWSBucketeer(None)

    raise ValueError(bootstrap_env)
