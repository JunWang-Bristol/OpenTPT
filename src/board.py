class Board():
    def factory(name, port):
        if name == "NUCLEO-H503RB":
            from boards.ST import NUCLEO_H503RB
            return NUCLEO_H503RB(port)

    def reset(self):
        raise NotImplementedError

    def get_version(self, channel_index):
        raise NotImplementedError
