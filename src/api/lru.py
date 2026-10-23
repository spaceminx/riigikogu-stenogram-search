"""Size-bounded dict for the API's in-process caches."""

import threading
from collections import OrderedDict

MISSING = object()


class LRUDict(OrderedDict):
    """Dict holding at most maxsize entries; the least recently used entry is evicted first.

    Cache keys come from request parameters, so a plain dict would grow without limit.
    Use get(key, MISSING) for lookups: a separate `in` check and `[]` read can race with
    an eviction in another request thread.
    """

    def __init__(self, maxsize: int):
        super().__init__()
        self.maxsize = maxsize
        self._lock = threading.Lock()

    def get(self, key, default=None):
        with self._lock:
            if key not in self:
                return default
            self.move_to_end(key)
            return super().__getitem__(key)

    def __setitem__(self, key, value):
        with self._lock:
            super().__setitem__(key, value)
            self.move_to_end(key)
            while len(self) > self.maxsize:
                self.popitem(last=False)

    def clear(self):
        with self._lock:
            super().clear()
