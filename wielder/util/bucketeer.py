#!/usr/bin/env python
import logging
import os

from botocore.exceptions import ClientError

from wielder.util.boto3_session_cache import boto3_client
from wielder.util.util import get_aws_session

DEFAULT_REGION = "us-east-2"


class Bucketeer:
    """
    This wrapper object was created mainly to retain the AMI session.
    We use MFA for development and the code is per process.
    It currently supports AWS S3, Later on we can add more Cloud providers
    """

    def __init__(self, conf=None):

        if conf is None:
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

    def download_objects(self, bucket_name, prefix='', dest='/tmp'):
        """
        Download a chunk of objects

        :param dest: local destination prefix
        :param prefix:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        try:

            names = self.get_object_names(bucket_name, prefix)

            for name in names:

                print(name)

                obj_path = name[:name.rindex('/')]
                pdest = f'{dest}/{obj_path}'
                print(obj_path)
                # create nested directory structure
                os.makedirs(pdest, exist_ok=True)

                # save file with full path locally
                self.s3.download_file(bucket_name, name, f'{dest}/{name}')

        except ClientError as e:
            logging.error(e)
            return False
        return True

    def delete_file(self, bucket_name, file_name):
        """Empty an S3 bucket
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

