#!/usr/bin/env python
import logging

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

    def upload_file(self, source, bucket_name, dest):

        with open(source, "rb") as f:
            self.s3.upload_fileobj(f, bucket_name, dest)

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

    def empty_bucket(self, bucket_name):
        """Empty an S3 bucket

        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        try:

            s3objects = self.s3.list_objects(Bucket=bucket_name)['Contents']

            for obj in s3objects:
                object_name = obj["Key"]
                print(f"trying to delete {object_name}")
                self.s3.delete_object(
                    Bucket=bucket_name,
                    Key=object_name
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

            self.empty_bucket(bucket_name)
            self.s3.delete_bucket(Bucket=bucket_name)

        except ClientError as e:
            logging.error(e)
            return False
        return True

    def ls(self):
        """
        Retrieve a list of existing buckets.
        :return: list of bucket names
        """

        response = self.s3.list_buckets()

        # Output the bucket names
        print('Existing buckets:')
        for bucket in response['Buckets']:
            print(f'  {bucket["Name"]}')

        return response['Buckets']


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    _bucket_name = 'gichi'

    _region = "us-east-2"
    b = Bucketeer(True)

    b.ls()

    b.create_bucket(bucket_name=_bucket_name, region=_region)
    #
    buckets = b.ls()

    for i in range(3):
        b.upload_file(f'/tmp/rabbit.txt', _bucket_name, f'tson{i}.txt')
        # print("sleeping")
        # time.sleep(5)

    # value = input(f"are you sure you want to delete buckets!\n only YES! will work")
    #
    # if value == 'YES!':
    #     for bucket in buckets:
    #         _name = bucket["Name"]
    #
    #         value = input(f"are you sure you want to delete: {_name}\nonly YES! will work")
    #
    #         if value == 'YES!':
    #             b.delete_bucket(bucket["Name"])
    #
    #     b.ls()
