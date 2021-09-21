import logging

import git
from wielder.util.commander import subprocess_cmd, async_cmd
from wielder.util.hocon_util import inject_vars
from wielder.util.log_util import setup_logging
from wielder.util.util import DirContext
from pyhocon import ConfigFactory as Cf


class WGit:

    def __init__(self, repo_path):

        self.repo_path = repo_path

        with DirContext(repo_path):

            latest_commit = async_cmd('git rev-parse --verify HEAD')[0][:-1]

            logging.info(latest_commit)
            self.commit = latest_commit

            branches = async_cmd('git branch')

            branch = 'HEAD'

            for b in branches:

                if b[0] == '*':

                    branch = b[1:-1]

            logging.info(branch)
            self.branch = branch

        logging.debug('akavish')

    def submodule_commit(self, sub):

        with DirContext(self.repo_path):

            _cmd = f'git ls-tree HEAD {sub}'

            comm = async_cmd(_cmd)

            comm = comm[0].split(' ')[2].split('\t')[0]
            print(comm)

            return comm

    def as_hocon_str(self):

        d = vars(self)

        b = inject_vars('', d)

        return 'git: {\n' + b + '\n}'

    def as_hocon(self):

        hs = self.as_hocon_injection()
        return Cf.parse_string(hs)

    def as_hocon_injection(self):

        d = vars(self)

        a = ''

        for k, v in d.items():

            a = f'{a}\ngit.{k}:{v}'

        return a


def is_repo(path):

    try:
        _ = git.Repo(path).git_dir
        return True
    except git.exc.NoSuchPathError:
        return False
    except git.exc.InvalidGitRepositoryError:
        return False


def clone_or_update(source, destination, name=None, branch='master', local=False):

    logging.info("\nclone_or_update_local_repository\n")

    should_clone = not is_repo(destination)

    logging.info(f"should_clone: {should_clone}")

    if should_clone:
        logging.info(f"Cloning {source} to subscription to: {destination}")

        if local:
            if name is not None:
                destination = destination.replace(name, '')
            subprocess_cmd(f"git -C {destination} clone {source}")
        else:
            subprocess_cmd(f"git clone {source} {destination}")
    else:
        logging.info("Subscription already has terraform submodule")

    subprocess_cmd(f"git -C {destination} stash")
    subprocess_cmd(f"git -C {destination} fetch")
    subprocess_cmd(f"git -C {destination} checkout {branch}")
    subprocess_cmd(f"git -C {destination} config pull.rebase false")
    subprocess_cmd(f"git -C {destination} pull")


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    logging.info('Configured logging')
    logging.debug('Configured logging')
