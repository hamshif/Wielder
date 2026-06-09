import logging


class WielderBase:

    def pretty(self):

        [logging.info(it) for it in self.__dict__.items()]


