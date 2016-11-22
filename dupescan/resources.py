import collections
import io


class StreamPool(object):
    class Stream(object):
        def __init__(self, pool, inst_id, path, offset=0):
            self._pool = pool
            self._inst_id = inst_id
            self.path = path
            self._offset = offset
            self._handle = None
            self.memo = None

        def _resume(self):
            assert self._handle is None, "Stream._resume called with open handle"
            self._pool._notify_will_open(self)
            self._handle = open(self.path, "rb")
            self._handle.seek(self._offset)

        def suspend(self):
            if self._handle is not None:
                self._offset = self._handle.tell()
                self._handle.close()
                self._handle = None
                self._pool._notify_did_close(self)

        def close(self):
            self.suspend()
            self._offset = 0
        
        def read(self, count):
            if self._handle is None:
                self._resume()
            return self._handle.read(count)

        def seek(self, offset, whence=io.SEEK_SET):
            if self._handle is None:
                if whence == io.SEEK_SET:
                    self._offset = offset
                    return

                if whence == io.SEEK_CUR:
                    self._offset += offset
                    if self._offset < 0:
                        self._offset = 0
                    return

                # otherwise we have a SEEK_END, in which case we need to open
                # the file, or an invalid argument, in which case it's better
                # to just use fh.seek() 's error handling. either way we need
                # to open the file and forward it to fh.seek(). 
                self._resume()

            self._handle.seek(offset, whence)
        
        def tell(self):
            if self._handle is None:
                return self._offset
            return self._handle.tell()

    def __init__(self, max_open_files):
        self.max_open_files = max_open_files
        self._open_instances = collections.OrderedDict()
        self._inst_id = 0

    def open(self, path, offset=0):
        stream = StreamPool.Stream(self, self._inst_id, path, offset)
        self._inst_id += 1
        return stream

    def _notify_will_open(self, stream):
        if len(self._open_instances) == self.max_open_files:
            for old_stream in self._open_instances.values():
                old_stream.suspend()
                break
        self._open_instances[stream._inst_id] = stream

    def _notify_did_close(self, stream):
        del self._open_instances[stream._inst_id]


def decide_max_open_files():
    try:
        import resource

        rid = None
        if hasattr(resource, "RLIMIT_NOFILE"):
            rid = resource.RLIMIT_NOFILE
        elif hasattr(resource, "RLIMIT_OFILE"):
            rid = resource.RLIMIT_OFILE

        if rid is not None:
            soft_limit, _ = resource.getrlimit(rid)
            if soft_limit == resource.RLIM_INFINITY:
                return 32768

            return max(1, int(soft_limit * 0.75))

    except ImportError:
        pass

    return 64
