from symphony.spec import ProcessGroupSpec
from .process import TmuxProcessSpec


class TmuxProcessGroupSpec(ProcessGroupSpec):
    def _new_process(self, *args, **kwargs):
        return TmuxProcessSpec(*args, **kwargs)

    @classmethod
    def load_dict(cls):
        pass

    def dump_dict(self):
        pass