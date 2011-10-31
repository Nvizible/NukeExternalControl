import os

SOCKET_BUFFER_SIZE = 4096
MAX_SOCKET_BYTES = 2048

# These constants set the default port range for any automatic searches.
DEFAULT_START_PORT = 54200
DEFAULT_END_PORT = 54300

# This constant should be set to whatever absolute or relative call your system
# uses to launch Nuke (excluding any flags or arguments).
NUKE_EXEC = os.getenv("NUKE_EXEC")
if NUKE_EXEC is None:
    NUKE_EXEC = 'Nuke'

# Safe type lists for pickling. Objects whose types are not included in one
# of these lists will be represented by proxy objects on the client side.
basicTypes = [int, float, complex, str, unicode, buffer, xrange, bool, type(None)]
listTypes = [list, tuple, set, frozenset]
dictTypes = [dict]

class NukeLicenseError(StandardError):
    pass

class NukeConnectionError(StandardError):
    pass

class NukeManagerError(NukeConnectionError):
    pass

class NukeServerError(NukeConnectionError):
    pass
