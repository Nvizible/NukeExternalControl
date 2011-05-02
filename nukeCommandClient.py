'''
This script defines the client-side classes for the Nuke command server interface.

It also functions as an executable for the purposes of launching NukeCommandManager
instances.
'''

import inspect
import pickle
import socket
import subprocess
import sys
import threading
import time
from os import devnull

basicTypes = [int, float, complex, str, unicode, buffer, xrange, bool, type(None)]
listTypes = [list, tuple, set, frozenset]
dictTypes = [dict]

# This constant should be set to whatever absolute or
# relative call your system uses to launch Nuke (excluding
# any flags or arguments).
NUKE_EXEC = 'Nuke'

MAX_SOCKET_BYTES = 16384

class NukeLicenseError(StandardError):
    pass

class NukeConnectionError(StandardError):
    pass

class NukeManagerError(NukeConnectionError):
    pass

class NukeServerError(NukeConnectionError):
    pass


class NukeConnection():
    '''
    If 'port' is specified, the client will attempt to connect
    to a command server on that port, raising an exception
    if one is not found.

    Otherwise, the standard port search routine runs.
    '''
    def __init__(self, port=None, host="localhost", instance=0):
        self._objects = {}
        self._functions = {}
        self._host = host
        self.is_active = False
        if not port:
            start_port = 54200 + instance
            end_port = 54300
            self._port = self.find_connection_port(start_port, end_port)
            if self._port == -1:
                raise NukeConnectionError("Connection with Nuke failed")
            self.is_active = True
        else:
            self._port = port
            if not self.test_connection():
                raise NukeConnectionError("Could not connect to Nuke command server on port %d" % self._port)
            self.is_active = True
    
    def find_connection_port(self, start_port, end_port):
        for port in range(start_port, end_port + 1):
            self._port = port
            if self.test_connection():
                return port
        return -1
    
    def send(self, data):#
        size = 1024 * 1024
        
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self._host, self._port))
            s.send(data)
            result = s.recv(size)
            s.close()
        except socket.error:
            raise NukeConnectionError("Connection with Nuke failed")
            
        return result
    
    def test_connection(self):
        try:
            self.get("test")
            return True
        except NukeConnectionError, e:
            return False
    
    def get(self, item_type, item_id = -1, parameters = None):
        try:
            data = {'action': item_type, 'id': item_id, 'parameters': parameters}
            encoded = pickle.dumps(self.encode(data))
            
            if len(encoded) > MAX_SOCKET_BYTES:
                encodedBits = []
                while encoded:
                    encodedBits.append(encoded[:MAX_SOCKET_BYTES])
                    encoded = encoded[MAX_SOCKET_BYTES:]
                
                for i in range(len(encodedBits)):
                    result = pickle.loads(self.send(pickle.dumps({'type': "NukeTransferPartialObject", 'part': i, 'part_count': len(encodedBits), 'data': encodedBits[i]})))
                    if i < (len(encodedBits) - 1):
                        if not (isinstance(result, dict) and 'type' in result and result['type'] == "NukeTransferPartialObjectRequest" and 'part' in result and result['part'] == i+1):
                            raise NukeConnectionError("Unexpected response to partial object")
            else:
                result = pickle.loads(self.send(encoded))

            if isinstance(result, dict) and 'type' in result and result['type'] == "NukeTransferPartialObject":
                data = result['data']
                nextPart = 1
                while nextPart < result['part_count']:
                    returnData = self.send(pickle.dumps({'type': "NukeTransferPartialObjectRequest", 'part': nextPart}))
                    result = pickle.loads(returnData)
                    data += result['data']
                    nextPart += 1
                
                result = pickle.loads(data)
        except Exception, e:
            raise e
        
        if isinstance(result, Exception):
            raise result
        
        return result
    
    def shutdown_server(self):
        '''
        Passes the 'shutdown' keyword to the server.
        This will raise a special exception in the
        server's listener loop, causing it to pass
        back a shutdown message, close the client,
        and exit cleanly.

        Returns whatever shutdown message the server
        sends back as a string.
        '''
        self.is_active = False
        return self.get('shutdown')

    def get_object_attribute(self, obj_id, property_name):
        return self.decode(self.get("getattr", obj_id, property_name))
    
    def set_object_attribute(self, obj_id, property_name, value):
        return self.decode(self.get("setattr", obj_id, (property_name, value)))
    
    def get_object_item(self, obj_id, property_name):
        return self.decode(self.get("getitem", obj_id, property_name))
    
    def set_object_item(self, obj_id, property_name, value):
        return self.decode(self.get("setitem", obj_id, (property_name, value)))
    
    def call_object_function(self, obj_id, parameters):
        return self.decode(self.get("call", obj_id, parameters))
    
    def get_object_length(self, obj_id):
        return self.decode(self.get("len", obj_id))
    
    def get_object_string(self, obj_id):
        return self.decode(self.get("str", obj_id))
    
    def get_object_repr(self, obj_id):
        return self.decode(self.get("repr", obj_id))
    
    def import_module(self, module_name):
        return self.decode(self.get("import", parameters = module_name))
    
    def recode_data(self, data, recode_object_func):
        if type(data) in basicTypes:
            return data
        elif type(data) in listTypes:
            newList = []
            for i in data:
                newList.append(self.recode_data(i, recode_object_func))
            return type(data)(newList)
        elif type(data) in dictTypes:
            if 'type' in data and data['type'] == "NukeTransferObject":
                return recode_object_func(data)
            else:
                newDict = {}
                for k in data:
                    newDict[self.recode_data(k, recode_object_func)] = self.recode_data(data[k], recode_object_func)
                return newDict
        else:
            return recode_object_func(data)
            
    def encode_data(self, data):
        return self.recode_data(data, self.encode_data_object)
    
    def decode_data(self, data):
        return self.recode_data(data, self.decode_data_object)
    
    def encode_data_object(self, data):
        if isinstance(data, NukeObject):
            return {'type': "NukeTransferObject", 'id': data._id}
        else:
            raise TypeError("Invalid object type being passed through connection: '%s'" % data)
    
    def decode_data_object(self, data):
        return NukeObject(self, data['id'])
    
    def encode(self, data):
        return self.encode_data(data)
    
    def decode(self, data):
        return self.decode_data(data)
    
    def __getattr__(self, attrname):
        return self.get_object_item(-1, attrname)

    def __getitem__(self, itemname):
        return self.__getattr__(itemname)

    def __repr__(self):
        return object.__repr__(self).replace("instance object", "NukeConnection instance")
    
    def __str__(self):
        return self.__repr__()

class NukeObject():
    def __init__(self, connection, id):
        self.__dict__['_id'] = id
        self.__dict__['_connection'] = connection
    
    def __getattr__(self, attrname):
        if attrname[0] == "_":
            return self.__dict__[attrname]
        else:
            return self._connection.get_object_attribute(self._id, attrname)
        
    def __setattr__(self, attrname, value):
        return self._connection.set_object_attribute(self._id, attrname, value)
        
    def __getitem__(self, itemname):
        return self._connection.get_object_item(self._id, itemname)
    
    def __setitem__(self, itemname, value):
        return self._connection.set_object_item(self._id, itemname, value)
    
    def __call__(self, *args, **kwargs):
        return self._connection.call_object_function(self._id, {'args': args, 'kwargs': kwargs})
    
    def __len__(self):
        return self._connection.get_object_length(self._id)
    
    def __str__(self):
        return self._connection.get_object_string(self._id)
    
    def __repr__(self):
        return self._connection.get_object_repr(self._id)


class NukeCommandManager():
    '''
    This class internally manages a Nuke command client-server pair.
    It is designed to be instantiated as the 'as' assignment in a
    'with' statement.

    Example usage:

        with NukeCommandManager() as conn:
            nuke = conn.nuke
            b = nuke.createNode('Blur')
            print b.writeKnobs()

    When it starts up, it establishes a manager socket on an
    available OS-assigned port.

    When the manager's __enter__ method is called, the server
    subprocess is started. The manager then waits for the managed
    server to call back with its status and bound port.

    A NukeConnection instance is then started using the port number
    returned by the managed server's callback. This instance is
    attached to the manager and returned to the 'with' statement.

    The body of the 'with' block is now executed,
    with the client instance available via the 'as' assignment.

    When the 'with' statement is complete, the client instance sends
    its companion server the 'shutdown' signal. This will cause the
    server to send back its shutdown message, close the connection to
    the client, and exit cleanly.

    The __exit__ method then waits for the server thread to exit by
    calling its '.join()' method.
    '''
    def __init__(self, license_retry_count=5, license_retry_delay=5):
        self.manager_port = -1
        self.manager_socket = None
        self.server_port = -1
        self.client = None
        self.license_retry_count = license_retry_count
        self.license_retry_delay = license_retry_delay
        self.nuke_stdout, self.nuke_stderr = None, None

        bound_port = False

        manager = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        manager.settimeout(10.0)
        manager.bind(('', 0))
        bound_port = True
        self.manager_port = manager.getsockname()[1]
        self.manager_socket = manager

        if (not bound_port) or (self.manager_port == -1):
            raise NukeManagerError("MANAGER: Cannot find port to bind to")

    def __enter__(self):
        if not self.manager_socket:
            raise NukeManagerError("Manager failed to initialize socket.")
        backlog = 5
        self.manager_socket.listen(backlog)

        # Start the server process and wait for it to call back to the 
        # manager with its success status and bound port
        self.start_server()

        self.manager_socket.close()
        try:
            self.client = NukeConnection(self.server_port)
        except:
            self.shutdown_server()
            raise
        return self.client

    def __exit__(self, type, value, traceback):
        self.client.shutdown_server()
        self.nuke_stdout, self.nuke_stderr = self.serverProc.communicate()

    def start_server(self):
        bufsize = 4096
        # Make sure the port number has a trailing space... this is a bug in Nuke's
        # Python argument parsing (logged with The Foundry as Bug 17918)
        procArgs = ([NUKE_EXEC, '-t', '-m', '1', '--', inspect.getabsfile(self.__class__), '%d ' % self.manager_port],)
        for i in xrange(self.license_retry_count+1):
            self.serverProc = subprocess.Popen(stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE,
                                               *procArgs)
            startTime = time.time()
            timeout = startTime + 10 # Timeout after 10 seconds of waiting for server
            try:
                while True:
                    try:
                        # This will time out after 10 seconds based on the socket settings
                        server, address = self.manager_socket.accept()
                    except socket.timeout:
                        retCode = self.serverProc.poll()
                        if retCode == 100: # License failure.
                            raise NukeLicenseError
                        else: # Nuke is either still running or dead for other reasons.
                            raise NukeManagerError("Server process failed to start properly.")
                    data = server.recv(bufsize)
                    if data:
                        serverData = pickle.loads(data)
                        server.close()
                        if not serverData[0]:
                            raise NukeServerError("Server could not find port to bind to.")
                        self.server_port = serverData[1]
                        break
                    if time.time() >= timeout:
                        raise NukeManagerError("Manager timed out waiting for server connection.")

            except NukeConnectionError, e:
                try:
                    self.shutdown_server()
                except Exception:
                    pass

                self.nuke_stdout, self.nuke_stderr = self.serverProc.communicate()
                e.nuke_sdout, e.nuke_stderr = self.nuke_stdout, self.nuke_stderr 
                raise

            except NukeLicenseError:
                print "License error. Retrying in %d seconds..." % self.license_retry_delay
                time.sleep(self.license_retry_delay)
            else:
                return

        raise NukeLicenseError("Maximum license retry count exceeded. Aborting.")

    def shutdown_server(self):
        '''
        Used to shut down a managed server if its
        client could not be initialized.
        Returns the server's shutdown message.
        '''
        bufsize = 1024 * 1024
        packet = {'action':'shutdown', 'id':-1, 'parameters':None}
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(('', self.server_port))
            s.send(pickle.dumps(packet))
            result = s.recv(bufsize)
            s.close()
            return pickle.loads(result)
        except socket.error:
            # Failed to connect to server port (server is dead?)
            raise NukeServerError("Server failed to initialize.")


def start_managed_nuke_server(manager_port=None):
    '''
    Convenience function for launching a managed Nuke command
    server instance that will communicate with a NukeCommandManager
    on the specified port. Must be called from within Nuke.
    '''
    import nukeCommandServer
    nukeCommandServer.NukeManagedServer(manager_port=manager_port)


if __name__ == '__main__':
    manager_port = None

    if len(sys.argv) > 1:
        manager_port = int(sys.argv[1])

    start_managed_nuke_server(manager_port)
