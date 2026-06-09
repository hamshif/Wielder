import os
import shutil
import tempfile
import unittest
import uuid
import hashlib
from pathlib import Path
from botocore.exceptions import ClientError
from pyhocon import ConfigFactory

from wielder.util.bucketeer import AWSBucketeer, DevBucketeer, GoogleBucketeer


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.uploaded_keys = []

    def head_object(self, Bucket, Key):
        object_key = (Bucket, Key)
        if object_key not in self.objects:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
        body = self.objects[object_key]
        return {
            "ContentLength": len(body),
            "ETag": f'"{self._md5(body)}"',
        }

    def upload_file(self, source, bucket_name, dest_key):
        self.objects[(bucket_name, dest_key)] = Path(source).read_bytes()
        self.uploaded_keys.append(dest_key)

    @staticmethod
    def _md5(body):
        digest = hashlib.md5()
        digest.update(body)
        return digest.hexdigest()


class TestAWSBucketeer(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.test_dir) / "source"
        (self.source_dir / "nested").mkdir(parents=True)
        (self.source_dir / "stable.txt").write_text("same")
        (self.source_dir / "changed.txt").write_text("new")
        (self.source_dir / "nested" / "added.txt").write_text("added")

        self.s3 = FakeS3Client()
        self.bucket_name = "test-bucket"
        self.s3.objects[(self.bucket_name, "prefix/stable.txt")] = b"same"
        self.s3.objects[(self.bucket_name, "prefix/changed.txt")] = b"old"

        self.bucketeer = AWSBucketeer.__new__(AWSBucketeer)
        self.bucketeer.s3 = self.s3

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_sync_directory_uploads_missing_and_changed_files(self):
        self.assertTrue(
            self.bucketeer.sync_directory(
                str(self.source_dir),
                self.bucket_name,
                "prefix",
            )
        )

        self.assertEqual(
            sorted(self.s3.uploaded_keys),
            ["prefix/changed.txt", "prefix/nested/added.txt"],
        )
        self.assertEqual(self.s3.objects[(self.bucket_name, "prefix/stable.txt")], b"same")
        self.assertEqual(self.s3.objects[(self.bucket_name, "prefix/changed.txt")], b"new")
        self.assertEqual(self.s3.objects[(self.bucket_name, "prefix/nested/added.txt")], b"added")

    def test_sync_directory_requires_directory_source(self):
        with self.assertRaises(ValueError):
            self.bucketeer.sync_directory(
                str(self.source_dir / "stable.txt"),
                self.bucket_name,
                "prefix",
            )

class TestDevBucketeer(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.bucket_name = "test-bucket"
        self.bucket_path = os.path.join(self.test_dir, self.bucket_name)
        os.makedirs(self.bucket_path)
        
        
        conf = ConfigFactory.parse_string(f'''
            buckets_root = "{self.test_dir}"
            namespace_bucket = "{self.bucket_name}"
        ''')
        self.bucketeer = DevBucketeer(conf=conf)
        self.bucketeer.root = self.test_dir

        # Create test mock geometries
        os.makedirs(os.path.join(self.bucket_path, "deep/nested/path"))
        
        with open(os.path.join(self.bucket_path, "deep/nested/path/target_file.json"), "w") as f:
            f.write("{}")
            
        with open(os.path.join(self.bucket_path, "root_file.txt"), "w") as f:
            f.write("root")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_object_exists_by_key_nested(self):
        # Should cleanly evaluate nested keys securely mapping to Prefix + Object Name under the hood
        target_key = "deep/nested/path/target_file.json"
        self.assertTrue(self.bucketeer.object_exists_by_key(self.bucket_name, target_key))

    def test_object_exists_by_key_root(self):
        # Should properly evaluate root-level keys without prefixes
        target_key = "root_file.txt"
        self.assertTrue(self.bucketeer.object_exists_by_key(self.bucket_name, target_key))

    def test_object_exists_by_key_missing(self):
        # Should safely terminate Boolean fallbacks for missing objects mimicking S3 constraints
        target_key = "deep/nested/path/missing_file.json"
        self.assertFalse(self.bucketeer.object_exists_by_key(self.bucket_name, target_key))

    def test_delete_object_if_exists_by_key_deletes_existing_object(self):
        state = self.bucketeer.delete_object_if_exists_by_key(
            self.bucket_name,
            "deep/nested/path/target_file.json",
        )

        self.assertTrue(state["exists"])
        self.assertTrue(state["deleted"])
        self.assertFalse(self.bucketeer.object_exists_by_key(self.bucket_name, "deep/nested/path/target_file.json"))

    def test_delete_object_if_exists_by_key_skips_missing_object(self):
        state = self.bucketeer.delete_object_if_exists_by_key(
            self.bucket_name,
            "deep/nested/path/missing_file.json",
        )

        self.assertFalse(state["exists"])
        self.assertFalse(state["deleted"])

class TestGoogleBucketeer(unittest.TestCase):
    def setUp(self):
        try:
            conf_str = '''
            google_credentials_path = "/tmp/wielder-google-credentials"
            '''
            self.bucketeer = GoogleBucketeer(conf=ConfigFactory.parse_string(conf_str))
            self.test_bucket_name = f"wielder_test_drive_{uuid.uuid4().hex[:8]}"
        except Exception as e:
            self.skipTest(f"Google Workspace credentials natively missing or configuration aborted: {e}")

    def tearDown(self):
        """Emergency catch to aggressively delete the Drive if the pipeline catastrophically crashes midway."""
        try:
            self.bucketeer.delete_bucket(self.test_bucket_name)
        except Exception:
            pass

    def test_shared_drive_lifecycle(self):
        """Validates the strict exist -> create -> exist -> delete -> exist topology natively via Drive API."""
        # 1. Assert Does Not Exist First
        self.assertFalse(self.bucketeer.bucket_exists(self.test_bucket_name), "Bucket inexplicably exists before creation!")
        print(f'{self.test_bucket_name} does not exist')
        # 2. Provision Bucket natively
        self.assertTrue(self.bucketeer.create_bucket(self.test_bucket_name), "Google Drive provisioning failed!")
        print(f'{self.test_bucket_name} was created')
        # 3. Assert Exists
        self.assertTrue(self.bucketeer.bucket_exists(self.test_bucket_name), "Bucket missing after direct creation API call!")
        print(f'{self.test_bucket_name} exists')
        
        # 4. Assert listed in get_bucket_names
        names = self.bucketeer.get_bucket_names()
        print(f'bucket names:\n {names}')
        self.assertIn(self.test_bucket_name, names, "Bucket name absent from global Google Drive API listing!")
        print(f'{self.test_bucket_name} is listed')
        # 5. Teardown
        self.assertTrue(self.bucketeer.delete_bucket(self.test_bucket_name), "Google Drive teardown hook aborted!")
        print(f'{self.test_bucket_name} was deleted')
        # 6. Assert Does Not Exist Finally
        self.assertFalse(self.bucketeer.bucket_exists(self.test_bucket_name), "Bucket inexplicably survived the delete payload!")
        print(f'{self.test_bucket_name} does not exist')
        

if __name__ == '__main__':
    print("Initiating absolute Manual Debugging Trace for GoogleBucketeer...")
    
    # Manually instantiate the test mapping to the precise lifecycle method
    test_pipeline = TestGoogleBucketeer('test_shared_drive_lifecycle')
    
    # Hardcode the evaluation execution manually bypassing PyTest isolation layers
    test_pipeline.setUp()
    try:
        test_pipeline.test_shared_drive_lifecycle()
        print("SUCCESS! Workspace Shared Drive TDD Trace completed entirely natively!")
    finally:
        # Guarantee teardown execution securely
        test_pipeline.tearDown()
