import logging
import os


def update_eks_context(runtime_env, cred_profile, region, kube_cluster_name):

    if runtime_env == 'aws':
        context_cmd = f'aws eks --profile {cred_profile} --region {region} ' \
                      f'update-kubeconfig --name {kube_cluster_name};'

        logging.info(f'Running Kubernetes context change command:\n{context_cmd}')

        os.system(context_cmd)

    elif runtime_env == 'gcp':
        logging.warning("Gaining context for GCP hasn't been written")
    elif runtime_env == 'azure':
        logging.warning("Gaining context for Azure hasn't been written")