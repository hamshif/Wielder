import logging

import git
from wielder.util.commander import subprocess_cmd
from wielder.util.log_util import setup_logging


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
