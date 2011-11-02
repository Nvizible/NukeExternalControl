'''
This module defines the server-side classes for the Nuke command server interface.

It can also be passed as an executable to automatically start server instances.
'''

import pickle
import socket
import threading
import imp
import nuke

from nukeExternalControl.common import *

VERIFY_CONNECTION_NONE = 0
VERIFY_CONNECTION_ALWAYS = 1
VERIFY_CONNECTION_ONLY_REMOTE = 2

def nuke_command_server(verifyConnection = VERIFY_CONNECTION_NONE):
    '''
    Launch the command server in a separate thread
    '''
    t = threading.Thread(None, NukeInternal, args = (verifyConnection,))
    t.setDaemon(True)
    t.start()
    
class NukeInternal(object):
    '''
    A class that runs inside of Nuke, and allows actions to be requested
    over a socket connection to a client.
    It deals with keeping track of any objects that cannot be passed over
    the socket and ensures that the client side feels as similar to running
    the code inside Nuke as possible.
    '''
    def __init__(self, port = None, verifyConnection = VERIFY_CONNECTION_NONE):
        self._objects = {}
        self._next_object_id = 0
        self._verify_connection = verifyConnection
        self.port = port
        self.bound_port = False
        
        host = ''
        backlog = 5
        if not self.port:
			start_port = DEFAULT_START_PORT
			end_port = DEFAULT_END_PORT
        else:
            start_port = end_port = self.port
        
        for port in xrange(start_port, end_port + 1):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                print "SERVER: Checking port %d" % port
                s.bind((host, port))
                self.bound_port = True
                self.port = port
                break
            except Exception, e:
                pass
        
        if not self.bound_port:
            raise NukeConnectionError("Cannot find port to bind to")
            
        s.listen(backlog)
        self.start_server(s)
        
    def start_server(self, sock):
        '''
        Starts the main server loop
        '''
        while 1:
            client, address = sock.accept()
            try:
				data = client.recv(SOCKET_BUFFER_SIZE)
				if data:
					result = self.receive(data)
					client.send(result)
            except SystemExit:
                result = self.encode('SERVER: Shutting down...')
                client.send(result)
                raise
            finally:
				client.close()
    
    def recode_data(self, data, recode_object_func):
        '''
        Recode some data with the passed recode function
        This deals with passing data both to and from the interim format,
        and recursively recoding lists and dictionaries.
        '''
        if type(data) in basicTypes or isinstance(data, Exception):
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
        '''
        Encode data to send back to the client
        '''
        return self.recode_data(data, self.encode_data_object)
    
    def decode_data(self, data):
        '''
        Decode data that the client has passed through
        '''
        return self.recode_data(data, self.decode_data_object)

    def encode_data_object(self, data):
        '''
        Encode an object that cannot be directly passed.
        Stores the object, and creates a dictionary with the
        id of the stored object
        '''
        this_object_id = self._next_object_id
        self._next_object_id += 1
        self._objects[this_object_id] = data
        return {'type': "NukeTransferObject", 'id': this_object_id}
    
    def decode_data_object(self, data):
        '''
        Gets a stored data object based on the passed id
        '''
        object_id = data['id']
        return self._objects[object_id]

    def encode(self, data):
        '''
        Encode some data, and turn it into a pickled stream
        '''
        return pickle.dumps(self.encode_data(data))
    
    def decode(self, data):
        '''
        Decode a pickle stream of data, ensuring that any Nuke objects are
        re-linked
        '''
        return self.decode_data(pickle.loads(data))

    def verify_connection(self, host):
        '''
        If the server has specified that new connections need to be verified by
        the user, pop up a dialog asking them if a connection can be made.
        '''
        if self._verify_connection == VERIFY_CONNECTION_NONE or \
                (self._verify_connection == VERIFY_CONNECTION_ONLY_REMOTE and \
                 host in ["localhost", os.getenv("HOST")]):
            return True
        
        # If Nuke isn't running in GUI mode, then allow the connection to verify
        if nuke.GUI:
            return nuke.executeInMainThreadWithResult(nuke.ask, ("Something is trying to connect to Nuke from %s.\nDo you wish to allow this?" % host,))
        
        return True
        
    def get(self, data):
        '''
        Perform whatever action is requested, and return the result
        '''
        obj = self.get_object(data['id'])
        params = data['parameters']
        result = None
        action = data['action']
        try:
            if data['action'] == "initiate":
                if self.verify_connection(params):
                    result = "accept"
                else:
                    result = "deny"
            elif data['action'] == "test":
                result = True
            elif data['action'] == "getattr":
                result = getattr(obj, params)
            elif action == "setattr":
                setattr(obj, params[0], params[1])
            elif action == "getitem":
                # If we're actually getting from globals(), then raise NameError instead of KeyError
                if data['id'] == -1 and params not in obj:
                    raise NameError("name '%s' is not defined" % params)
                result = obj[params]
            elif action == "setitem":
                obj[params[0]] = params[1]
            elif action == "call":
                result = nuke.executeInMainThreadWithResult(obj, args=params['args'], kwargs=params['kwargs'])
            elif action == "len":
                result = len(obj)
            elif action == "str":
                result = str(obj)
            elif action == "repr":
                result = `obj`
            elif data['action'] == "del":
                del obj
            elif data['action'] == "isinstance":
                result = obj.__instancecheck__(params)
            elif data['action'] == "issubclass":
                result = issubclass(params, obj)
            elif action == "import":
                result = imp.load_module(params, *imp.find_module(params))
            elif action == "shutdown":
                # This keyword triggers the server shutdown
                raise SystemExit
        except Exception, e:
            result = e
        
        return result
    
    def receive(self, data_string):
        '''
        Receive the pickled data that has been sent by the client, and
        do whatever needs to be done with it.
        If the data is being passed through as a multi-part transfer, store
        the parts so far and send back a request for the rest.
        Also, when sending data back, deal with splitting it up into a multi-part
        message if it is too long.
        '''
        data = self.decode(data_string)
        
        if isinstance(data, dict) and 'type' in data and data['type'] == "NukeTransferPartialObjectRequest":
            if data['part'] in self.partialObjects:
                encoded = self.partialObjects[data['part']]
                del self.partialObjects[data['part']]
                return encoded
        
        if isinstance(data, dict) and 'type' in data and data['type'] == "NukeTransferPartialObject":
            if data['part'] == 0:
                self.partialData = ""
            self.partialData += data['data']
            
            if data['part'] == (data['part_count'] - 1):
                data = pickle.loads(self.partialData)
            else:
                nextPart = data['part'] + 1
                return pickle.dumps({'type': "NukeTransferPartialObjectRequest", 'part': nextPart})
            
        encoded = self.encode(self.get(data))
        
        if len(encoded) > MAX_SOCKET_BYTES:
            encodedBits = []
            while encoded:
                encodedBits.append(encoded[:MAX_SOCKET_BYTES])
                encoded = encoded[MAX_SOCKET_BYTES:]
            
            self.partialObjects = {}
            for i in range(len(encodedBits)):
                self.partialObjects[i] = pickle.dumps({'type': "NukeTransferPartialObject", 'part': i, 'part_count': len(encodedBits), 'data': encodedBits[i]})
            
            encoded = self.partialObjects[0]
            del self.partialObjects[0]

        return encoded

        
    def get_object(self, id):
        '''
        Get the stored object with the appropriate id.
        If the id is -1, then get the globals
        '''
        if id == -1:
            return globals()
        else:
            return self._objects[id]


class NukeManagedServer(NukeInternal):
    '''
    Subclass of the Nuke Command Server designed to be managed
    by a NukeCommandManager. It adds constructor arguments for
    a manager port and a manager hostname.

    Once it has initialized, and immediately before the main
    server loop is started, it sends a status "packet" to the
    manager on 'manager_port,' which informs the manager whether
    the server has successfully bound itself to a port, and
    which port it is using.
    '''
    def __init__(self, port=None, manager_port=None, manager_host='localhost'):
        self.manager_port = manager_port
        self.manager_host = manager_host
        NukeInternal.__init__(self, port, VERIFY_CONNECTION_NONE)

    def start_server(self, socket):
        '''
        Fires the manager callback, then starts
        the main server loop.
        '''
        self.manager_callback(self.bound_port)
        NukeInternal.start_server(self, socket)

    def manager_callback(self, status):
        '''
        Tell the manager what port the server ended up
        binding to so the client can connect to the
        correct server instance.

        'status' is a boolean indicating whether the server
        succeeded in binding to a port.
        '''
        if not self.manager_port:
            return
        manager = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        manager.connect((self.manager_host, self.manager_port))
        manager.send(self.encode((status, self.port)))
        manager.close()
        if not status:
            raise NukeConnectionError("Cannot find port to bind to")


if __name__ == '__main__':
    NukeInternal()
