import logging

import git
import os
from pyhocon import ConfigFactory as Cf
from wielder.util.commander import subprocess_cmd, async_cmd
from wielder.util.log_util import setup_logging
from wielder.util.util import DirContext


class WGit:

    def __init__(self, repo_path):

        self.repo_path = repo_path

        with DirContext(repo_path):

            dir_name = repo_path.split(os.sep)[-1]

            latest_commit = async_cmd('git rev-parse --verify HEAD')[0][:-1]

            logging.info(f'latest_commit for {dir_name}: {latest_commit}')
            self.commit = latest_commit

            branches = async_cmd('git branch')

            branch = 'HEAD'

            for b in branches:

                if b[0] == '*':

                    branch = b[1:-1].strip()

            self.branch = branch

    def get_submodule_commit(self, sub):

        with DirContext(self.repo_path):

            _cmd = f'git ls-tree HEAD {sub}'

            submodule_pointer = async_cmd(_cmd)
            if len(submodule_pointer) == 0:
                return None

            submodule_pointer = submodule_pointer[0].split(' ')[2].split('\t')[0]
            logging.info(f'submodule {sub} pointer commit: {submodule_pointer}')

            return submodule_pointer

    def get_submodule_names(self):

        with DirContext(self.repo_path):
            awk_cmd = 'gawk' if os.system('gawk --version') == 0 else 'awk'
            print_line = '{ print $2 }'
            _cmd = f"git config --file .gitmodules --get-regexp path | {awk_cmd} '{print_line}'"

            response = async_cmd(_cmd)
            submodule_names = []

            for submodule_name in response:
                submodule_names.append(submodule_name.replace('\n', ''))

            logging.info(response)

            return submodule_names

    def update_submodules(self):

        with DirContext(self.repo_path):

            _cmd = 'git submodule update --init --recursive'

            response = async_cmd(_cmd)

            logging.info(response)

            return response

    def update_submodule(self, sub_path):

        with DirContext(self.repo_path):

            _cmd = f'git submodule update --init -- {sub_path}'

            response = async_cmd(_cmd)

            logging.info(response)

            return response

    def get_diff(self, sub):

        sub_path = f'{self.repo_path}/{sub}'

        with DirContext(sub_path):

            _cmd = f'git status'

            status = async_cmd(_cmd)

            print(status)

    def as_hocon(self):

        hs = self.as_hocon_injection()
        return Cf.parse_string(hs)

    def as_hocon_injection(self):

        d = vars(self)

        a = ''

        for k, v in d.items():

            a = f'{a}\ngit.{k}:{v}'

        return a

    def as_dict_injection(self):

        d = vars(self)

        injection = {'git': {'subs': {}}}

        for k, v in d.items():

            injection['git'][k] = v

        for sub in self.get_submodule_names():

            injection['git']['subs'][sub] = self.get_submodule_commit(sub)

        return injection


def is_repo(path):

    try:
        _ = git.Repo(path).git_dir
        return True
    except git.exc.NoSuchPathError:
        return False
    except git.exc.InvalidGitRepositoryError:
        return False


def clone_or_update(source, destination, name=None, branch='master', commit_sha=None, local=False):

    logging.info("\nclone_or_update_local_repository\n")

    should_clone = not is_repo(destination)

    logging.info(f"should_clone: {should_clone}")

    if should_clone:
        logging.info(f"Cloning {source} to: {destination}")

        if local:
            if name is not None:
                destination = destination.replace(name, '')
            subprocess_cmd(f"git -C {destination} clone {source}")
        else:
            subprocess_cmd(f"git clone {source} {destination}")
    else:
        logging.info("Destination already has git repo")

    revert = branch
    if commit_sha is not None:
        revert = commit_sha

    subprocess_cmd(f"git -C {destination} stash")
    subprocess_cmd(f"git -C {destination} fetch")
    subprocess_cmd(f"git -C {destination} checkout {revert}")
    subprocess_cmd(f"git -C {destination} config pull.rebase false")

    if commit_sha is None:
        subprocess_cmd(f"git -C {destination} pull")


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    logging.info('Configured logging')
    logging.debug('Configured logging')
