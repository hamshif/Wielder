
class WielderBase:

    def pretty(self):

        [print(it) for it in self.__dict__.items()]