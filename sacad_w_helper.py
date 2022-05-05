#!/usr/bin/env python3
# py -3 ./sacad_w_helper.py

'''
sacad_w :: helper component
	open artwork image, open folder location & clipboard copy for manual review
'''

import sys, os, socket, ssl, time
import _thread, threading, string
import subprocess, signal, re
import hashlib, uuid, zipfile
import pathlib, pyclip
import _config as _

def normCopy(_str):
	translator = str.maketrans(string.punctuation, ' '*len(string.punctuation))
	_words = (_str.translate(translator)).split()
	return ' '.join([word for word in _words if word.lower() not in CLIP_EXCL])

def termProcess(p, _pid):
	if _pid is not None:
		if p.poll() is None:
			try: p.terminate()
			except: pass
	return None

# https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
def getLocalIP():
	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		s.connect(("8.8.8.8", 80))
		_ip = s.getsockname()[0]
		s.close()
	except:
		return '127.0.0.1'
	else:
		return _ip

class Mapper():
	def __init__(self, str=None):
		self.str = str

	# public
	def map(self):
		return self._map(self._normalize(self.str))

	# private
	def _map(self, _str, swap=False):
		for _k, _v in _.cfg.HELP_MAP.items():
			if swap: _k, _v = _v, _k
			k = self._normalize(_k)
			if k in _str:
				patt = re.compile(re.escape(k), re.IGNORECASE)
				test = os.path.normpath(patt.sub(self._normalize(_v, lc=False), self.str))
				if test.startswith('\\'): test = '\\' + test
				elif test.startswith('//'): test = test[1:]
				if os.path.exists(test): return test
		if swap: return self.str
		return self._map(_str, swap=True)

	def _normalize(self, str, lc=True):
		if lc: return ('/'.join(re.split(r'\/+|\\+', str))).lower()
		return '/'.join(re.split(r'\/+|\\+', str))
# end Mapper()

class StopThreadEvent(Exception):
    pass

class COM(threading.Thread):
	def __init__(self):
		super(COM, self).__init__()

		self.stopEv = threading.Event()

		# subprocessing
		self.p = None
		self.pid = None

		# temp working copy
		self.ofid = None
		self.of = None

		# TLS wrapper
		self.tlscf = os.path.join(_sd, 'sacad_w.crt')
		self.tlskf = os.path.join(_sd, 'sacad_w.key')
		self.tlspf = os.path.join(_sd, 'sacad_w.pem')
		self.ssl = False
		self.ssl_context = None
		self._setupContext()

		# socket in blocking mode
		self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.port = BIND_PORT
		try:
			self.s.bind(('', self.port))
		except (socket.error, msg):
			raise StopThreadEvent
		self.s.listen(5)

	def stop(self):
		self._makeTmp() # clean up
		self.stopEv.set()

	def run(self):
		while not self.stopEv.is_set():
			# setup procedures
			if not self.ssl:
				self._awaitSSLKeys()
				continue

			# regular ops
			self.s = self.ssl_context.wrap_socket(self.s, server_side=True)
			try:
				c, addr = self.s.accept()
				c.send('READY'.encode())
			except Exception as e:
				print(e)
				continue
			data = c.recv(4096)

			if data:
				try:
					data = data.decode('utf-8')
				except:
					self._termProcess()
					image_data = [data]
					while True:
						try:
							bytes_read = c.recv(4096)
						except:
							bytes_read = None
						if not bytes_read: break
						image_data.append(bytes_read)
					# pil.show() won't yield a handle; following is a better solution
					image_data = b''.join(image_data)
					self._makeTmp()
					with open(self.of, mode='wb') as f: f.write(image_data)
					print(self.of)
					if os.path.isfile(self.of):
						self.p = subprocess.Popen([VIEWER_BIN, self.of], shell=False)
						self.pid = self.p.pid
				else:
					if data.startswith('id='):
						self._termProcess()
						data = data.split('=', 1)[1]
						if (len(data) == 32):
							_if = os.path.join(_.cfg.HELP_TMP, "%s.jpg" % (data,))
							print(_if)
							if os.path.isfile(_if):
								self.p = subprocess.Popen([VIEWER_BIN, _if], shell=False)
								self.pid = self.p.pid
					elif data.startswith('file='):
						self._termProcess()
						data = data.split('=', 1)[1]
						if not os.path.isfile(os.path.normpath(data)): data = Mapper(data).map()
						data = os.path.normpath(data)
						print(data)
						if os.path.isfile(data):
							self.p = subprocess.Popen([VIEWER_BIN, data], shell=False)
							self.pid = self.p.pid
					elif data.startswith('dir='):
						data = data.split('=', 1)[1]
						if not os.path.isdir(os.path.normpath(data)): data = Mapper(data).map()
						data = os.path.normpath(data)
						print(data)
						if os.path.isdir(data):
							if CLIP:
								try:
									pdirname = (pathlib.PurePath(data)).name
									if len(pdirname) <= 15:
										pyclip.copy(normCopy((pathlib.Path(data)).parent.name + ' ' + pdirname))
									else:
										pyclip.copy(normCopy(pdirname))
								except:
									print('clip copy failed, see https://pypi.org/project/pyclip/')
							if os.name == 'nt':
								# https://docs.python.org/3.6/library/os.html#os.startfile
								os.startfile(os.path.normpath(data))
							# tbd: posix implementation
					elif data.startswith('sig=int') or data.startswith('sig=iter'):
						# clean up
						self._makeTmp()
						self._termProcess()
					elif data.startswith('sig=ping'): pass
					elif data.startswith('sig=kill'):
						# clean up
						self._makeTmp()
						self._termProcess()
						raise SystemExit
				# end ELSE
			# end IF
			c.close()
		# end WHILE

	def _makeTmp(self):
		if self.of and os.path.isfile(self.of):
			os.remove(self.of)
		self.ofid = "%s" % (hashlib.md5((uuid.uuid1().hex).encode('utf-8')).hexdigest(),)
		self.of = os.path.join(_sd, "%s.jpg" % (self.ofid,))

	def _termProcess(self):
		if self.pid is not None: self.pid = termProcess(self.p, self.pid)

	def _awaitSSLKeys(self):
		c, addr = self.s.accept()
		c.send('READY'.encode())
		# expect a zip including all files
		zip_data = []
		while True:
			try:
				bytes_read = c.recv(4096)
			except:
				bytes_read = None
			if not bytes_read: break
			zip_data.append(bytes_read)
		c.close()
		zip_data = b''.join(zip_data)

		zipid = "%s" % (hashlib.md5((uuid.uuid1().hex).encode('utf-8')).hexdigest(),)
		zipf = os.path.join(_sd, "%s.zip" % (zipid,))
		with open(zipf, mode='wb') as f: f.write(zip_data)
		if zipfile.is_zipfile(zipf):
			# looks reasonable, purge obsolete files..
			try:
				os.remove(self.tlscf)
				os.remove(self.tlskf)
				os.remove(self.tlspf)
			except: pass
			# ..extract and verify
			with zipfile.ZipFile(zipf, 'r') as zip:
				zip.printdir()
				zip.extractall()
			if  os.path.isfile(self.tlscf) and  \
				os.path.isfile(self.tlskf) and  \
				os.path.isfile(self.tlspf): self._setupContext()
		os.remove(zipf)

	def _setupContext(self):
		try:
			# basic TLS will do
			self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH, cafile=self.tlscf)
			self.ssl_context.verify_mode = ssl.CERT_REQUIRED
			self.ssl_context.load_cert_chain(self.tlspf)
		except FileNotFoundError:
			print("awaiting key exchange")
		else:
			self.ssl = True

if __name__ == "__main__":
	print("sacad_w :: helper\npress ctrl+c to exit")

	_ip = getLocalIP()
	if _ip not in _.cfg.HELP_CLIENTS:
		print("error: no config for %s" % (_ip,))
		sys.exit(1)

	BIND_PORT = _.cfg.HELP_CLIENTS[_ip]['BIND_PORT']
	VIEWER_BIN = _.cfg.HELP_CLIENTS[_ip]['VIEWER_BIN']

	CLIP = _.cfg.HELP_CLIENTS[_ip]['CLIP']
	if CLIP:
		CLIP_EXCL = []
		for word in _.cfg.HELP_CLIP_EXCL:
			CLIP_EXCL.append(word.lower())

	_sd = os.path.dirname(os.path.realpath(__file__))
	os.chdir(_sd)

	cworker = COM()
	cworker.daemon = True
	cworker.start()

	try:
		while 1:
			if not cworker.is_alive(): break
			time.sleep(0.3)
		# end LOOP
	except (KeyboardInterrupt, SystemExit):
		print("Shut down on SIGINT.")
	except Exception as e:
		print("Shut down on RUNTIME_ERROR: %s" % (str(e)))
	else:
		print("Shut down.")
	finally:
		if (cworker is not None and cworker.is_alive()):
			try:
				cworker.stop()
				i = 0
				while cworker.is_alive():
					i += 1
					if i > 10: break
					time.sleep(0.1)
			except: pass
		sys.exit(0)
