import logging
import os
import pathlib
from abc import ABC, abstractmethod

from botocore.exceptions import ClientError
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from tabulate import tabulate
from tqdm import tqdm

import wielder.util.util as wu
from wielder.util.boto3_session_cache import boto3_client
from wielder.util.google_drive import service_login
from wielder.util.util import get_aws_session
from wielder.wield.enumerator import RuntimeEnv, local_deployments
from wielder.wield.project import WielderProject

# todo if we decide on that, add dependencies to be installed automatically

DEFAULT_REGION = "us-east-2"


class Bucketeer(ABC):

    def __init__(self, conf):
        self.conf = conf

    @abstractmethod
    def create_bucket(self, bucket_name, region=None):
        pass

    @abstractmethod
    def cli_upload_file(self, source, bucket_name, dest):
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
    def cli_download_object(self, bucket_name, key, dest):
        pass

    @abstractmethod
    def download_objects(self, bucket_name, keys, dest='/tmp'):
        pass

    @abstractmethod
    def download_objects_by_key(self, bucket_name, root_key='', dest='/tmp'):
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

    @abstractmethod
    def object_exists(self, bucket_name, prefix, object_name):
        pass

    @abstractmethod
    def bucket_sync(self, src_bucket, dest_bucket, src_prefix, dest_prefix):
        pass


class AWSBucketeer(Bucketeer):
    """
    A convenience interface for working with AWS buckets.
    This wrapper object was created mainly to retain the AMI session.
    We use MFA for development and the code is per process.
    It currently supports AWS S3.
    """

    def __init__(self, conf=None, auth=True):

        super().__init__(conf)

        if auth:
            session = get_aws_session(conf)
            self.s3 = session.resource('s3').meta.client
        else:
            logging.info('Direct auth not needed, getting default client.')
            self.s3 = boto3_client(service_name='s3')

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

    def cli_upload_file(self, source, bucket_name, dest):

        _cmd = f'aws s3 cp {source} "s3://{bucket_name}/{dest}" --profile {self.conf.aws_cli_profile}'
        logging.info(f'Running command:\n{_cmd}')
        #would work in Windows?
        os.system(_cmd)

    def upload_file(self, source, bucket_name, dest):

        with wu.open_data_path(source, "rb") as f:
            self.s3.upload_fileobj(f, bucket_name, dest)

    def upload_directory(self, source, bucket_name, prefix):

        for root, dirs, files in wu.walk(source):
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

            # print(name)

            # create nested directory structure
            wu.makedirs(dest, exist_ok=True)

            # save file with full path locally
            self.s3.download_file(bucket_name, f'{key}/{name}', f'{dest}/{name}')

        except ClientError as e:
            logging.error(e)
            # return False
        return True

    def cli_download_object(self, bucket_name, key, dest):

        _cmd = f'aws s3 cp "s3://{bucket_name}/{key}" {dest} --profile {self.conf.aws_cli_profile}'
        logging.info(f'Running command:\n{_cmd}')
        os.system(_cmd)

    def download_objects(self, bucket_name, keys, dest='/tmp'):
        """
        Download a chunk of objects

        :param keys:
        :param dest: local destination prefix
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """

        for key in tqdm(keys):

            obj_path = key[:key.rindex('/')]

            obj_name = key.split('/')[-1]
            logging.debug(f'obj_path: {obj_path}\nobj_name: {obj_name}')

            ok = self.download_object(bucket_name, obj_path, obj_name, dest)
            if not ok:
                return False

        return True

    def download_objects_by_key(self, bucket_name, root_key='', dest='/tmp'):
        """
        Download a chunk of objects

        :param dest: local destination prefix
        :param root_key:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """

        names = self.get_object_names(bucket_name, root_key)

        return self.download_objects(bucket_name, names, dest)

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

            paginator = self.s3.get_paginator('list_objects_v2')
            response = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

            object_names = []

            for responses in response:
                s3objects = responses['Contents']
                for obj in s3objects:
                    object_name = obj["Key"].rstrip()
                    logging.debug(f'Object name: {object_name}')
                    object_names.append(object_name)

            return object_names

        except KeyError as e:
            logging.error(e)
            logging.info(f"No objects in key {prefix}")

    def object_exists(self, bucket_name, prefix, object_name):

        object_names = self.get_object_names(
            bucket_name=bucket_name,
            prefix=prefix
        )

        if f'{prefix}/{object_name}' in object_names:
            return True

        return False

    def bucket_sync(self, source, dest, src_prefix, dest_prefix=None):

        if dest_prefix is None:
            dest_prefix = src_prefix

        _cmd = f'aws s3 sync "s3://{source}/{src_prefix}" "s3://{dest}/{dest_prefix}" --profile {self.conf.aws_cli_profile}'
        logging.info(f'Running command:\n{_cmd}')
        os.system(_cmd)


class GoogleBucketeer(Bucketeer):
    """
    A mock bucket object
    The class emulates a cloud bucket by performing similar functionality on
    A directory
    """

    def __init__(self, conf=None, auth=True):

        super().__init__(conf)

        self.service = service_login(conf)

    def _get_folder_id(self, folder_name):
        """ not ready yet. does not support non-unique names"""
        folder_list = self.service.files().list(q=f"name='{folder_name}'",
                                                spaces="drive",
                                                fields="nextPageToken, files(id, name, mimeType)").execute()
        folder_id = None
        for folder in folder_list['files']:
            if folder['name'] == folder_name:
                folder_id = folder['id']
                break
        if folder_id is None:
            raise Exception('Folder name not found.')
        else:
            return folder_id

    def get_size_format(b, factor=1024, suffix="B"):
        """
        Scale bytes to its proper byte format
        e.g:
            1253656 => '1.20MB'
            1253656678 => '1.17GB'
        """
        for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
            if b < factor:
                return f"{b:.2f}{unit}{suffix}"
            b /= factor
        return f"{b:.2f}Y{suffix}"

    def list_files(self, items):
        """given items returned by Google Drive API, prints them in a tabular way"""
        if not items:
            return "No files available."
        else:
            rows = []
            for item in items:
                id = item["id"]
                name = item["name"]
                try:
                    parents = item["parents"]
                except:
                    parents = "N/A"
                try:
                    size = self.get_size_format(int(item["size"]))
                except:
                    size = "N/A"
                mime_type = item["mimeType"]
                modified_time = item["modifiedTime"]
                rows.append((id, name, parents, size, mime_type, modified_time))
            return tabulate(rows, headers=["ID", "Name", "Parents", "Size", "Type", "Modified Time"])

    def create_bucket(self, bucket_name, region=None):
        pass

    def cli_upload_file(self, source, bucket_name, dest):
        pass

    def create_folder(self, folder_name):
        """ Create a folder and prints the folder ID
        Returns : Folder Id
        """

        try:
            # create drive api client
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }

            # pylint: disable=maybe-no-member
            file = self.service.files().create(body=file_metadata, fields='id').execute()
            return file.get('id')

        except HttpError as error:
            print(f'An error occurred: {error}')
            return None

    def upload_file(self, source, file_name, dest):
        try:
            folder_id = self._get_folder_id(dest)
        except:
            folder_id = self.create_folder(dest)
            print(f'No existing folder found. Created folder {dest}.')
        file = MediaFileUpload(f'{source}/{file_name}', resumable=True)

        file_metadata = {'name': file_name, "parents": [folder_id]}
        file = self.service.files().create(body=file_metadata, media_body=file, fields='id').execute()
        print("File created, id:", file.get("id"))

        return True

    def upload_directory(self, source, bucket_name, prefix):

        wu.copytree(source, f'{self.buckets_root}/{bucket_name}/{prefix}')

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
            wu.makedirs(dest, exist_ok=True)
            src = f'{self.buckets_root}/{bucket_name}/{key}/{name}'

            if wu.isfile(src):

                stale = f'{dest}/{name}'
                wu.remove(stale)

                wu.copy(src, dest)

        except Exception as e:
            logging.error(e)
            return False
        return True

    def cli_download_object(self, bucket_name, key, dest):
        pass

    def download_objects(self, bucket_name, names, dest='/tmp'):
        """

        Copies a list of files to a destination to mimic downloading objects

        :param dest: local destination prefix
        :param names: list of files
        :param bucket_name: Bucket
        :return: True
        """

        wu.makedirs(dest, exist_ok=True)

        for name in names:

            dest1 = f'{dest}/{name}'

            wu.remove(dest1)

            src = f'{bucket_name}/{name}'
            wu.copyfile(src, dest)

    def download_objects_by_key(self, bucket_name, root_key='', dest='/tmp'):
        """
        Copies A directory emulating download of a chunk of objects from cloud bucket

        :param dest: local destination prefix
        :param root_key:
        :param bucket_name: Bucket
        :return: True
        """
        wu.rmtree(dest, ignore_errors=True)
        wu.copytree(f'{self.buckets_root}/{bucket_name}/{root_key}', dest)

        return True

    def delete_file(self, bucket_name, file_name):
        """Delete a file to emulate deleting a bucket object
        :param file_name:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """

        wu.rmtree(f'{self.buckets_root}/{bucket_name}/{file_name}', ignore_errors=True)

        return True

    def delete_objects(self, bucket_name, prefix=''):
        """Empty a local Dir emulating a bucket

        :param prefix:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        wu.rmtree(f'{self.buckets_root}/{bucket_name}/{prefix}', ignore_errors=True)

        return True

    def delete_bucket(self, bucket_name):
        """Delete an S3 bucket by emptying it and deleting the empty bucket.

        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """

        wu.rmtree(f'{self.buckets_root}/{bucket_name}', ignore_errors=True)

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

    def object_exists(self, bucket_name, prefix, object_name):

        names = self.get_object_names(
            bucket_name=bucket_name,
            prefix=prefix
        )

        for name in names:
            if str(name).rstrip() == object_name:
                return True

        return False

    def bucket_sync(self, src_bucket, dest_bucket, src_prefix, dest_prefix):
        # TODO: Fill function
        pass


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
        wu.makedirs(f'{self.buckets_root}/{bucket_name}', exist_ok=True)

        return True

    def cli_upload_file(self, source, bucket_name, dest):
        pass

    def upload_file(self, source, bucket_name, dest):

        dir_path = dest[:dest.rfind('/')]
        file_path = f'{self.buckets_root}/{bucket_name}/{dir_path}'
        wu.makedirs(file_path, exist_ok=True)

        wu.copy(source, f'{self.buckets_root}/{bucket_name}/{dest}')

    def upload_directory(self, source, bucket_name, prefix):

        wu.copytree(source, f'{self.buckets_root}/{bucket_name}/{prefix}')

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
            wu.makedirs(dest, exist_ok=True)
            src = f'{self.buckets_root}/{bucket_name}/{key}/{name}'

            if wu.isfile(src):

                stale = f'{dest}/{name}'
                wu.remove(stale)

                wu.copy(src, dest)

        except Exception as e:
            logging.error(e)
            return False
        return True

    def cli_download_object(self, bucket_name, key, dest):
        pass

    def download_objects(self, bucket_name, names, dest='/tmp'):
        """

        Copies a list of files to a destination to mimic downloading objects

        :param dest: local destination prefix
        :param names: list of files
        :param bucket_name: Bucket
        :return: True
        """

        wu.makedirs(dest, exist_ok=True)

        for name in names:

            dest1 = f'{dest}/{name}'

            wu.remove(dest1)

            src = f'{bucket_name}/{name}'
            wu.copyfile(src, dest)

    def download_objects_by_key(self, bucket_name, root_key='', dest='/tmp'):
        """
        Copies A directory emulating download of a chunk of objects from cloud bucket

        :param dest: local destination prefix
        :param root_key:
        :param bucket_name: Bucket
        :return: True
        """
        wu.rmtree(dest, ignore_errors=True)
        wu.copytree(f'{self.buckets_root}/{bucket_name}/{root_key}', dest)

        return True

    def delete_file(self, bucket_name, file_name):
        """Delete a file to emulate deleting a bucket object
        :param file_name:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """

        wu.rmtree(f'{self.buckets_root}/{bucket_name}/{file_name}', ignore_errors=True)

        return True

    def delete_objects(self, bucket_name, prefix=''):
        """Empty a local Dir emulating a bucket

        :param prefix:
        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """
        wu.rmtree(f'{self.buckets_root}/{bucket_name}/{prefix}', ignore_errors=True)

        return True

    def delete_bucket(self, bucket_name):
        """Delete an S3 bucket by emptying it and deleting the empty bucket.

        :param bucket_name: Bucket to deleted
        :return: True if bucket deleted, else False
        """

        wu.rmtree(f'{self.buckets_root}/{bucket_name}', ignore_errors=True)

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
            full_path = f'{self.buckets_root}/{bucket_name}/{prefix}'
            bucket_names = [str(p) for p in wu.get_files_in_dir(full_path) if p.is_dir()]

            return bucket_names

        except KeyError as e:
            logging.error(e)
            logging.info(f"No objects in key {prefix}")

    def object_exists(self, bucket_name, prefix, object_name):

        names = self.get_object_names(
            bucket_name=bucket_name,
            prefix=prefix
        )

        for name in names:
            if str(name).rstrip() == object_name:
                return True

        return False

    def bucket_sync(self, src_bucket, dest_bucket, src_prefix, dest_prefix):
        # TODO: Fill function
        pass


def get_bucketeer(conf, runtime_env=RuntimeEnv.MAC, bucket_env=RuntimeEnv.AWS):
    """
    Factory method for standardizing bucket access e.g. S3 boto3 client, GCP Client, Local Directory to simulate bucket,
     depending on the combination of runtime environment and deploy environment.
    :param conf: project config
    :param runtime_env: Where this code is running
    :param bucket_env: Where the bucket is.
    :return: a Bucketeer object wrapping buckets or local mock buckets
    """

    if runtime_env.value in local_deployments:
        auth = True
    else:
        auth = False

    if bucket_env == RuntimeEnv.AWS:
        return AWSBucketeer(conf, auth=auth)
    else:
        return DevBucketeer(conf)

