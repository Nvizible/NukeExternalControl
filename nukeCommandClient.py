import pickle
import socket

basicTypes = [int, float, complex, str, unicode, buffer, xrange, bool, type(None)]
listTypes = [list, tuple, set, frozenset]
dictTypes = [dict]

class NukeConnection:
	def __init__(self):
		self._objects = {}
		self._functions = {}
		
	def send(self, data):
		host = 'localhost'
		port = 54261
		size = 1024 * 1024
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.connect((host, port))
		s.send(data)
		result = s.recv(size)
		s.close()
		return result
	
	def get(self, item_type, item_id, parameters):
		try:
			data = {'action': item_type, 'id': item_id, 'parameters': parameters}
			returnData = self.send(pickle.dumps(self.encode(data)))
			result = pickle.loads(returnData)
		except Exception, e:
			raise e
		
		if isinstance(result, Exception):
			raise result
		
		return result
	
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
		return self.decode(self.get("len", obj_id, None))
	
	def get_object_string(self, obj_id):
		return self.decode(self.get("str", obj_id, None))
	
	def get_object_repr(self, obj_id):
		return self.decode(self.get("repr", obj_id, None))
	
	def import_module(self, module_name):
		return self.decode(self.get("import", -1, module_name))
	
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


class NukeObject:
	def __init__(self, connection, id):
		self.__dict__['_id'] = id
		self.__dict__['_connection'] = connection
	
	def __getattr__(self, attrname):
		if attrname[0] in self.__dict__:
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
