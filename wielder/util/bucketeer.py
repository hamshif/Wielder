#!/usr/bin/env python
import logging
import os

import boto3
from botocore.exceptions import ClientError

from wielder.util.boto3_session_cache import boto3_client
from wielder.util.log_util import setup_logging

DEFAULT_REGION = "us-east-2"


class Bucketeer:
    """
    This wrapper object was created mainly to retain the AMI session.
    We use MFA for development and the code is per process.
    It currently supports AWS S3, Later on we can add more Cloud providers
    """

    def __init__(self, use_existing_cred=False):

        if use_existing_cred:
            self.s3 = boto3_client(service_name='s3')
        else:
            self.s3 = boto3.client('s3')

    def create_bucket(self, bucket_name, region=None):
        """Create an S3 bucket in a specified region

        If a region is not specified, the bucket is created in the S3 default
        region (us-east-1).

        :param bucket_name: Bucket to create
        :param region: String region to create bucket in, e.g.p, 'us-east-2'
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
                self.s3.upload_file(os.path.join(root, file), bucket_name, f'{prefix}{file}')

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


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    _bucket_name = 'pep-dev-test'

    _region = "us-east-2"
    b = Bucketeer(True)

    b.get_bucket_names()

    b.create_bucket(bucket_name=_bucket_name, region=_region)
    #
    buckets = b.get_bucket_names()

    for i in range(3):
        b.upload_file(f'/tmp/rabbit.txt', _bucket_name, f'tson{i}.txt')
        # print("sleeping")
        # time.sleep(5)

    value = input(f"are you sure you want to delete buckets!\n only YES! will work")

    if value == 'YES!':

        b.delete_bucket(_bucket_name)
