import pickle
import socket
import threading
import imp
import nuke

basicTypes = [int, float, complex, str, unicode, buffer, xrange, bool, type(None)]
listTypes = [list, tuple, set, frozenset]
dictTypes = [dict]

MAX_SOCKET_BYTES = 16384

class NukeConnectionError(StandardError):
    pass

def nuke_command_server():
    t = threading.Thread(None, NukeInternal)
    t.setDaemon(True)
    t.start()
    
class NukeInternal:
    def __init__(self):
        self._objects = {}
        self._next_object_id = 0
        
        host = ''
        start_port = 54200
        end_port = 54300
        backlog = 5
        size = 1024 * 1024
        
        bound_port = False
        for port in range(start_port, end_port + 1):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                print "Trying port %d" % port
                s.bind((host, port))
                bound_port = True
                break
            except Exception, e:
                pass
        
        if not bound_port:
            raise NukeConnectionError("Cannot find port to bind to")
            
        s.listen(backlog)
        
        while 1:
            client, address = s.accept()
            data = client.recv(size)
            if data:
                result = self.receive(data)
                client.send(result)
            client.close()
    
    def recode_data(self, data, recode_object_func):
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
        return self.recode_data(data, self.encode_data_object)
    
    def decode_data(self, data):
        return self.recode_data(data, self.decode_data_object)

    def encode_data_object(self, data):
        this_object_id = self._next_object_id
        self._next_object_id += 1
        self._objects[this_object_id] = data
        return {'type': "NukeTransferObject", 'id': this_object_id}
    
    def decode_data_object(self, data):
        object_id = data['id']
        return self._objects[object_id]

    def encode(self, data):
        encoded_data = self.encode_data(data)
        return pickle.dumps(encoded_data)
    
    def decode(self, data):
        return self.decode_data(pickle.loads(data))

    def get(self, data):
        obj = self.get_object(data['id'])
        params = data['parameters']
        result = None
        try:
            if data['action'] == "getattr":
                result = getattr(obj, params)
            elif data['action'] == "setattr":
                setattr(obj, params[0], params[1])
            elif data['action'] == "getitem":
                # If we're actually getting from globals(), then raise NameError instead of KeyError
                if data['id'] == -1 and params not in obj:
                    raise NameError("name '%s' is not defined" % params)
                result = obj[params]
            elif data['action'] == "setitem":
                obj[params[0]] = params[1]
            elif data['action'] == "call":
                result = nuke.executeInMainThreadWithResult(obj, args=params['args'], kwargs=params['kwargs'])
            elif data['action'] == "len":
                result = len(obj)
            elif data['action'] == "str":
                result = str(obj)
            elif data['action'] == "repr":
                result = `obj`
            elif data['action'] == "import":
                result = imp.load_module(params, *imp.find_module(params))
        except Exception, e:
            result = e
        
        return result
    
    def receive(self, data_string):
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
        if id == -1:
            return globals()
        else:
            return self._objects[id]
