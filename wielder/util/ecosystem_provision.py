import logging
from wielder.util.bucketeer import get_ecosystem_bucketeer

def provision_ecosystem_buckets(conf):
    """
    Parses the `provision` block natively evaluated from the PyHocon ecosystem configuration 
    and checks or creates the necessary target abstractions structurally.
    """
    provision_conf = conf.get("provision", None)
    if not provision_conf:
        return

    for target_namespace, namespace_config in provision_conf.items():
        dry_run = namespace_config.get_bool("dry_run", False)
        buckets_to_create = namespace_config.get("buckets", None)
        
        if not buckets_to_create:
            continue
            
        if target_namespace == "google_workspace":
            bucketeer = get_ecosystem_bucketeer(conf, bucketeer_type="GoogleBucketeer")
        elif target_namespace == "gcp_gcs":
            bucketeer = get_ecosystem_bucketeer(conf, bucketeer_type="GCSBucketeer")
        elif target_namespace == "aws_s3":
            bucketeer = get_ecosystem_bucketeer(conf, bucketeer_type="AWSBucketeer")
        elif target_namespace == "local_os":
            bucketeer = get_ecosystem_bucketeer(conf, bucketeer_type="DevBucketeer")
        else:
            bucketeer = get_ecosystem_bucketeer(conf)

        bucketeer_type = type(bucketeer).__name__
        surface_map = {
            "GoogleBucketeer": "Google Workspace Shared Drives",
            "GCSBucketeer": "Google Cloud Storage",
            "AWSBucketeer": "AWS S3 Cloud Object Storage",
            "DevBucketeer": "Local OS Filesystem Emulation",
            "LocalBucketeer": "Local OS Filesystem Emulation"
        }
        target_surface = surface_map.get(bucketeer_type, "Unknown Cloud Surface")
        source_surface = conf.ecosystem

        logging.info(f"Initiating Multi-Surface Ecosystem Provisioning: [ {source_surface} => {target_surface} ]")

        for bucket_name in buckets_to_create:
            if bucketeer.bucket_exists(bucket_name):
                logging.info(f"[{source_surface} => {target_surface}] Target Bucket '{bucket_name}' safely validated online.")
            else:
                if dry_run:
                    logging.info(f"[DRY RUN - VALIDATION] [{source_surface} => {target_surface}] Would physically provision missing bucket dynamically: {bucket_name}")
                    # bucketeer.create_bucket(bucket_name)
                else:
                    logging.info(f"[{source_surface} => {target_surface}] Provisioning missing physical bucket dynamically natively: {bucket_name}")
                    bucketeer.create_bucket(bucket_name)
