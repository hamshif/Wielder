import os


class DirContext:
    """
    Written by Ido Goodis
    Context manager for changing the current working directory
    """

    def __init__(self, newPath):
        self.newPath = os.path.expanduser(newPath)

    def __enter__(self):
        self.savedPath = os.getcwd()
        os.chdir(self.newPath)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.savedPath)


def replace_last(full, sub, rep=''):

    end = ''
    count = 0
    for c in reversed(full):
        count = count + 1
        end = c + end
        # print(end)

        if sub in end:
            return full[:-count] + end.replace(sub, rep)

    return full
