
class Oscilloscope():
    def factory(name, port):
        if name == "PicoScope2408B":
            from oscilloscopes.PicoScope import PicoScope2408B
            return PicoScope2408B(port)

    def check_channel_index(self, channel_index):
        raise NotImplementedError

    def reset(self):
        raise NotImplementedError

    def get_version(self, channel_index):
        raise NotImplementedError
