import logging
import os
from pathlib import Path
from pyhocon import ConfigTree
from wielder.util.wgit import WGit

logger = logging.getLogger(__name__)

class WGitDag:
    """
    Agentic Git Orchestrator.
    Executes high-level DAG sequences for multi-repo state management.
    """

    def __init__(self, conf: ConfigTree):
        self.conf = conf
        self.super_repo_root = conf.super_repo_root
        self.wgit = WGit(self.super_repo_root)

    def init_feature(self, name: str, feature_type: str = "feature"):
        """
        DAG 1: Init Feature across the entire fleet.
        """
        branch_name = f"{feature_type}/{name}/main"
        logger.info(f"Initializing Journey: {branch_name}")
        
        # 1. Stash all
        self.wgit.async_cmd("git stash")
        self.wgit.async_cmd("git submodule foreach 'git stash'")
        
        # 2. Sync to trunks and pull
        # Note: This logic depends on the git.repo_policy defined in conf
        policy = self.conf.git.repo_policy
        
        # Super-repo sync
        trunk = policy.culture.trunk
        self.wgit.async_cmd(f"git checkout {trunk}")
        self.wgit.async_cmd(f"git pull origin {trunk}")
        
        # Submodules sync
        for sub in self.wgit.get_submodule_names():
            if sub in policy:
                sub_trunk = policy[sub].trunk
                logger.info(f"Syncing submodule {sub} to trunk {sub_trunk}")
                self.wgit.async_cmd(f"cd {sub} && git checkout {sub_trunk} && git pull origin {sub_trunk}")

        # 3. Create feature branch everywhere
        self.wgit.async_cmd(f"git checkout -b {branch_name}")
        self.wgit.async_cmd(f"git submodule foreach 'git checkout -b {branch_name}'")
        
        # 4. Update developer.conf
        dev_conf_path = os.path.join(self.super_repo_root, "conf/developer/developer.conf")
        with open(dev_conf_path, "w") as f:
            f.write(f'git.active_feature = "{branch_name}"
')
            
        logger.info(f"Journey Started! Active feature locked in {dev_conf_path}")

    def save_commit(self, user_message: str):
        """
        DAG 2: Save Commit with semantic metadata.
        """
        logger.info("Executing Semantic Seal...")
        msg = self.wgit.get_commit_message(self.conf, user_message)
        
        # 1. Add and commit submodules first
        for sub in self.wgit.get_submodule_names():
            logger.info(f"Sealing submodule: {sub}")
            self.wgit.async_cmd(f"cd {sub} && git add . && git commit -m "{msg}"")
            
        # 2. Commit super-repo
        logger.info("Sealing Super-Repo")
        self.wgit.async_cmd(f"git add .")
        self.wgit.async_cmd(f"git commit -m "{msg}"")
        logger.info("Fleet work sealed successfully.")

    def switch_node(self, node: str):
        """
        DAG 3: Diverge to a new node (sub-branch) of the current feature.
        """
        current_feature = self.conf.git.active_feature
        parts = current_feature.split('/')
        if len(parts) < 3:
            raise ValueError(f"Invalid active_feature format: {current_feature}")
            
        new_feature = f"{parts[0]}/{parts[1]}/{node}"
        logger.info(f"Switching Journey Node: {current_feature} -> {new_feature}")
        
        # 1. Branch from current state
        self.wgit.async_cmd(f"git checkout -b {new_feature}")
        self.wgit.async_cmd(f"git submodule foreach 'git checkout -b {new_feature}'")
        
        # 2. Update developer.conf
        dev_conf_path = os.path.join(self.super_repo_root, "conf/developer/developer.conf")
        with open(dev_conf_path, "w") as f:
            f.write(f'git.active_feature = "{new_feature}"
')
            
        logger.info(f"Node Switched! Current node is now '{node}'.")
