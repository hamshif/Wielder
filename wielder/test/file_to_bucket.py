#!/usr/bin/env python
import logging


from wielder.util.bucketeer import AWSBucketeer
from wielder.util.log_util import setup_logging

if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    _bucket_name = 'pep-dev-test'

    _region = "us-east-2"
    b = AWSBucketeer(None)

    b.get_bucket_names()

    b.create_bucket(bucket_name=_bucket_name, region=_region)

    buckets = b.get_bucket_names()

    for i in range(3):
        b.upload_file(f'/tmp/rabbit.txt', _bucket_name, f'tson{i}.txt')
        # print("sleeping")
        # time.sleep(5)

    value = input(f"are you sure you want to delete buckets!\n only YES! will work")

    if value == 'YES!':

        b.delete_bucket(_bucket_name)
