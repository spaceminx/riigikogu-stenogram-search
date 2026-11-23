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
        # key -> [lock, number of threads holding or waiting for it]
        self._key_locks: dict = {}
        self._key_locks_guard = threading.Lock()

    def get_or_compute(self, key, compute):
        """Return the cached value, or compute and store it once.

        After a sync clears the caches, concurrent first requests for the same key used to
        each run the same aggregate; now one computes and the others wait for its result.
        """
        value = self.get(key, MISSING)
        if value is not MISSING:
            return value
        with self._key_locks_guard:
            entry = self._key_locks.setdefault(key, [threading.Lock(), 0])
            entry[1] += 1
        try:
            with entry[0]:
                value = self.get(key, MISSING)
                if value is MISSING:
                    value = compute()
                    self[key] = value
                return value
        finally:
            with self._key_locks_guard:
                entry[1] -= 1
                if entry[1] == 0:
                    del self._key_locks[key]

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
