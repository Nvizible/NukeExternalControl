import pickle
import socket
import threading
import imp

basicTypes = [int, float, complex, str, unicode, buffer, xrange, bool, type(None)]
listTypes = [list, tuple, set, frozenset]
dictTypes = [dict]

def nuke_command_server():
  t = threading.Thread(None, NukeInternal)
  t.start()

class NukeInternal:
	def __init__(self):
		self._objects = {}
		self._next_object_id = 0
		
		host = ''
		port = 54261
		backlog = 5
		size = 1024 * 1024
		
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.bind((host, port))
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

	def get(self, data_string):
		data = self.decode(data_string)
		obj = self.get_object(data['id'])
		params = data['parameters']
		result = None
		try:
			if data['action'] == "getattr":
				result = getattr(obj, params)
			elif data['action'] == "setattr":
				setattr(obj, params[0], params[1])
			elif data['action'] == "getitem":
				# If we're actually getting from vars(), then raise NameError instead of KeyError
				if data['id'] == -1 and params not in obj:
					raise NameError("name '%s' is not defined" % params)
				result = obj[params]
			elif data['action'] == "setitem":
				obj[params[0]] = params[1]
			elif data['action'] == "call":
				result = obj(*params['args'], **params['kwargs'])
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
		
		encoded = self.encode(result)
		
		return encoded
	
	def receive(self, data):
		return self.get(data)
		
	def get_object(self, id):
		if id == -1:
			return globals()
		else:
			return self._objects[id]
