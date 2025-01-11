#!/usr/bin/env python3
'''
Semiautomatic Cover Art Dispatcher / Wrapper :: v.0.2.0 | author: robot
	feat. sacad (github.com/desbma/sacad) wrapper | extract from tags | symlink existing | image editing
	does not modify or update any data source

----- use case
	you want a correct folder.jpg in every album folder, e.g. for use with github.com/sentriz/gonic

----- synopsis
sacad_w.py -l|d <library|folder_path> && sacad_w.py -i && sacad_w.py -rc
	-> scan / fetch / extract -> run interactivist mode -> restore mod times -> clean up
	library scan excludes root directory; use -d to scan a subtree

----- future
interactive mode
	unavailable helper: shorter timeout, stop trying, check in background
	editor
		add image enhancements like brightness, and include unsafe ops
	on symlink decline and no embedded try fetch and ask
	helper
		handle errors, such as 'OSError: cannot write mode RGBA as JPEG'
			specifically relevant for HELP_PREF_NET (filetypes not jpeg)
scan
	--quicker mode to additionally skip tags, ambience, ..
	re/scan:
		offset: more testing with focus on speed and correctness
		resume: refactor to speed up
	may add option to exclude locations (interactive -> store?)
	pretty colors for errors and notices
misc.
	TLS dispatch keys scenarios:
		both helpers on same address
		helper running on localhost
	--max <int> to stop at total number of covers written
	check dependencies (sacad) version
	TLS improvements / robust protocol: https://bit.ly/33FskSI

----- known issues
JSON store not ideal for very large jobs; may use sqlite3 instead
sacad
	matching poorly / bad quality
	slow; may consider threading/multiprocessing
'''

import sys, os, io, time, datetime, shutil, json, re, zipfile, traceback
import subprocess, hashlib, uuid, filetype, PIL, argparse
import socket, ssl, functools, readline, _thread, threading
import _config as _
from PIL import Image
from pathlib import Path, PurePath
# https://pypi.org/project/termcolor/
from termcolor import colored

class Object(object): pass

CoverFile = Object()
library = None
lf = None
args = None
store = {}


class StopThreadEvent(Exception): pass
class GenSSLKeysException(Exception): pass

class COM():
	def __init__(self):
		self.tlscf = os.path.join(_sd, 'sacad_w.crt')
		self.tlskf = os.path.join(_sd, 'sacad_w.key')
		self.tlspf = os.path.join(_sd, 'sacad_w.pem')
		self.ssl_context = None
		self._setupContext()

	# public
	def genSSLKeys(self):
		try:
			if os.path.isfile(self.tlscf): os.remove(self.tlscf)
			if os.path.isfile(self.tlskf): os.remove(self.tlskf)
			if os.path.isfile(self.tlspf): os.remove(self.tlspf)
			os.chdir(_sd)
			p = subprocess.Popen([_.cfg.BIN['openssl'], 'req', '-new', '-newkey', 'rsa:4096', '-x509', '-days', '3650', '-nodes',
				'-subj', _.cfg.TLS_SUBJ,
				'-out', self.tlscf,
				'-keyout', self.tlskf
			])
			p.wait()
			if not os.path.isfile(self.tlskf): raise GenSSLKeysException("File does not exist: " % (self.tlskf,))
			os.system("%s %s %s > %s" % (_.cfg.BIN['cat'], self.tlscf, self.tlskf, self.tlspf))
			if not os.path.isfile(self.tlspf): raise GenSSLKeysException("File does not exist: " % (self.tlspf,))
		except Exception as e:
			print(colored(f"error: {e}", 'red'))
		else:
			if self._dispatchSSLKeys():
				print(colored("success. files copied to helper(s)", 'green'))
			else:
				print(colored("success. copy files to helper(s): %s, %s, %s" % (os.path.basename(self.tlspf), os.path.basename(self.tlscf), os.path.basename(self.tlskf)), 'green'))

	def chat(self, payload):
		if len(payload) > 4096:
			self._send(payload, hv_addr, hv_port)
		elif payload.startswith(b'dir='):
			self._chat(payload, _addr=he_addr, _port=he_port)
		elif payload.startswith(b'sig=kill'):
			self._chat(payload, _addr=he_addr, _port=he_port)
			self._chat(payload, _addr=hv_addr, _port=hv_port)
		elif payload.startswith(b'sig=ping'):
			self._chat(payload, _addr=he_addr, _port=he_port, _verbose=True)
			self._chat(payload, _addr=hv_addr, _port=hv_port, _verbose=True)
		else:
			self._chat(payload, _addr=hv_addr, _port=hv_port)

	# private
	def _chat(self, _msg, _addr=None, _port=None, _verbose=False):
		dbg = []
		if _addr is None or _port is None: return
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
			with self.ssl_context.wrap_socket(sock, server_side=False) as h_sock:
				try:
					h_sock.settimeout(_.cfg.HELP_CLIENTS[_addr]['TIMEOUT'])
					h_sock.connect((_addr, _port))
					if _verbose:
						dbg.append("%s:%s" % (_addr, _port))
						dbg.append("SSL: %s" % (h_sock.version(),))
				except Exception as e:
					if _verbose:
						dbg.append("%s:%s" % (_addr, _port))
						dbg.append(colored(e, 'red'))
				else:
					data = h_sock.recv(1024).decode()
					if data:
						h_sock.send(_msg)
						if _verbose: dbg.append(colored("%s" % (data,), 'green'))
					try: h_sock.close()
					except: pass
				finally:
					if _verbose: print(",\t".join(dbg))

	def _send(self, _bstr, _addr=None, _port=None):
		if _addr is None or _port is None: return
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
			with self.ssl_context.wrap_socket(sock, server_side=False) as h_sock:
				h_sock.settimeout(_.cfg.HELP_CLIENTS[_addr]['TIMEOUT'])
				try: h_sock.connect((_addr, _port))
				except: pass
				else:
					data = h_sock.recv(1024).decode()
					if data:
						for _bytes in self._chunkstring(_bstr, 4096):
							h_sock.sendall(_bytes)
						try: h_sock.close()
						except: pass

	def _chunkstring(self, _str, _len):
		return (_str[0+i:_len+i] for i in range(0, len(_str), _len))

	def _dispatchSSLKeys(self):
		_r = True
		zipid = "%s" % (hashlib.md5((uuid.uuid1().hex).encode('utf-8')).hexdigest(),)
		zipf = os.path.join(_sd, "%s.zip" % (zipid,))
		try:
			with zipfile.ZipFile(zipf, "w") as zip:
				zip.write(self.tlscf, os.path.basename(self.tlscf), compress_type = zipfile.ZIP_DEFLATED)
				zip.write(self.tlskf, os.path.basename(self.tlskf), compress_type = zipfile.ZIP_DEFLATED)
				zip.write(self.tlspf, os.path.basename(self.tlspf), compress_type = zipfile.ZIP_DEFLATED)
			with open(zipf, mode='rb') as f:
				_bstr = f.read()
			for _addr in _.cfg.HELP_CLIENTS:
				with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as h_sock:
					try: h_sock.connect((_addr, _.cfg.HELP_CLIENTS[_addr]['BIND_PORT']))
					except: _r = False
					else:
						data = h_sock.recv(1024).decode()
						if data:
							for _bytes in self._chunkstring(_bstr, 4096):
								h_sock.sendall(_bytes)
							try: h_sock.close()
							except: pass
			os.remove(zipf)
		except: _r = False
		return _r

	def _setupContext(self):
		try:
			self.ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=self.tlscf)
			self.ssl_context.load_cert_chain(self.tlspf)
			self.ssl_context.check_hostname = False
		except FileNotFoundError:
			self.genSSLKeys()
			_exit(0, True)
# end COM()

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

# @instantiate once // not thread safe
class FetchImageURL():
	def __init__(self):
		self.url = None

	# public
	# mandatory check before running get()
	def isValidURL(self, _str=None):
		if _str is None: return False
		try:
			_str = _str.strip()
			if ((not _str.startswith('https://') and not _str.startswith('http://')) or len(_str) < 18):
				raise ValueError
		except:
			self.url = None
			return False
		else:
			self.url = _str
			return True

	# assumes chdir used before calling
	def get(self):
		if self.url is None: return False
		_url = self.url
		self.url = None
		p = subprocess.Popen([_.cfg.BIN['curl'],
			'--silent',
			'-L',
			'-A',
			'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:94.0) Gecko/20100101 Firefox/94.0',
			'-o',
			'folder.jpg',
			_url
		])
		p.wait()
		if os.path.isfile('folder.jpg'): return True
		return False
# end FetchImageURL()

class ImageEditor():
	def __init__(self, path=None):
		# the input file
		self.fn = path
		# last argument string
		self.larg = None
		# argument stack
		self.stack = []
		# temp working copy
		self.ofid = None
		self.of = None

	# public
	def feed(self):
		_feed = "Image editor:\t\t\tType %s to confirm. Supported commands:\n\t\t\t\t%s = rotate left 90°\n\t\t\t\t%s = rotate right 90°\n\t\t\t\t%s = crop|split (in half) AND keep left\n\t\t\t\t%s = crop|split (in half) AND keep right\n\t\t\t\t%s = trim left|right|top|bottom by <int> pixels\n\t\t\t\t%s = resize target (%spx)\n\t\t\t\t%s = alt. quality\n> " % (colored('y[es]', 'green'), colored('rl', 'yellow'), colored('rr', 'green'), colored('cl|sl', 'yellow'), colored('cr|sr', 'green'), colored('t[l|r|t|b]<int>', 'yellow'), colored('res', 'green'), _.cfg.IMG['size'], colored('q', 'yellow'))
		clear()
		while 1:
			_code, _feed = self._input(_feed)
			if _code == 1:
				clear()
				break
			elif _code == -1:
				if self._process(self.larg):
					# referencing a newly created files isn't robust enough
					with open(self.of, mode='rb') as f: com.chat(f.read())
			else:
				clear()
				break
		if _code == 1: return self.of
		return None

	# private
	# deal with input. this typically feeds a loop
	def _input(self, _str):
		_in = input(_str)
		# affirmative
		if 'y' in _in.lower():
			return 1, ''
		# edit
		elif len(_in.strip()):
			self.larg = _in
			return -1, "\n> "
		# negative
		else:
			return 0, ''

	def _process(self, str=''):
		'''
		@arg str : space-delimited arguments string
		----------------------------------
		rl = rotate left 90°
		rr = rotate right -//-
		cl|sl = crop|split (in half)	AND keep left
		cr|sr = -//-					AND keep right
		tl<int> = trim left	by <int> pixels
		tr<int> = trim right -//-
		tt<int> = trim top -//-
		tb<int> = trim bottom -//-
		res = resize target (_.cfg.IMG['size'])
		q = alt. quality
		'''
		self.stack = str.split()
		if (self.fn is None or not len(self.stack)): return False;
		self._makeTmp()
		# copy is needed
		im = None
		qalt = False
		try:
			while self.stack:
				arg = (self.stack.pop(0)).lower()
				if im is None:
					with Image.open(self.fn) as h: im = h.copy()
				# https://stackoverflow.com/a/58350508
				if 'rl' in arg:
					im = im.rotate(90, expand=1)
				elif 'rr' in arg:
					im = im.rotate(270, expand=1)
				elif ('cl' in arg or 'sl' in arg):
					w, h = im.size
					im = im.crop((0, 0, int(w/2), h))
				elif ('cr' in arg or 'sr' in arg):
					w, h = im.size
					im = im.crop((int(w/2), 0, w, h))
				elif 'res' in arg:
					w, h = im.size
					if w > _.cfg.IMG['size']:
						im = PIL.ImageOps.contain(im, (_.cfg.IMG['size'], _.cfg.IMG['size']))
				elif (arg.startswith('t') and len(arg) >= 3):
					sub = arg[1:2] # l|r|t|b
					pix = int(arg[2:])
					if pix <= 0: continue
					w, h = im.size
					if 'l' in sub:
						im = im.crop((pix, 0, w, h))
					elif 'r' in sub:
						im = im.crop((0, 0, w - pix, h))
					elif 't' in sub:
						im = im.crop((0, pix, w, h))
					elif 'b' in sub:
						im = im.crop((0, 0, w, h - pix))
				elif 'q' in arg:
					qalt = True
			# end WHILE
			if im is None: raise ValueError
			if qalt:
				im.save(self.of, quality=85, subsampling=0)
			else:
				im.save(self.of)
		except:
			return False
		else:
			return True

	# need to create new hashes per edit session, since the client os may cache files
	def _makeTmp(self):
		if self.of and os.path.isfile(self.of):
			os.remove(self.of)
		self.ofid = "%s" % (hashlib.md5((uuid.uuid1().hex).encode('utf-8')).hexdigest(),)
		self.of = os.path.join(_.cfg.TMP, "%s.jpg" % (self.ofid,))
# end ImageEditor()

class Scan(threading.Thread):
	def __init__(self):
		super(Scan, self).__init__()
		self.stopEv = threading.Event()

	def stop(self):
		self.stopEv.set()

	def run(self):
		# handle StopThreadEvent
		try: self._goScan()
		except: pass

	def _goScan(self):
		global lf, store
		dirs = []

		print("sacad_w | %s" % ("logging to %s" % (_.cfg.LOG,) if lf is not None else "log disabled",))
		if args['quick']: printl('notice: using quick mode')
		elif args['magnetic']: printl('notice: using magnetic mode')
		if tscan: printl('notice: using time offset')
		if lf is not None: lf.write("\nsacad_w | %s" % (datetime.datetime.now(),))

		# load the storefile
		if not os.path.isfile(_.cfg.STORE):
			with io.open(_.cfg.STORE, 'w', encoding='utf8') as mf: mf.write('{}')
		with io.open(_.cfg.STORE, 'r', encoding='utf8') as mf:
			mfdata = mf.read()
		store = json.loads(mfdata)

		# pre-scan ambient nesting
		tree = {}
		for _root, _dirs, _files in os.walk(library):
			if self.stopEv.is_set(): raise StopThreadEvent
			if tscan and getMTime(_root) < tscan:
				_dirs[:] = []
				_files[:] = []

			tree[hashlib.md5(_root.encode('utf-8')).hexdigest()] = 0
			_parent = os.path.abspath(os.path.join(_root, os.pardir))
			for file in _files:
				if isAudioFile(file.lower()):
					try:
						tree[hashlib.md5(_parent.encode('utf-8')).hexdigest()] += 1
					except:
						tree[hashlib.md5(_parent.encode('utf-8')).hexdigest()] = 0
					break
			# end FOR
		# end FOR

		# main scan
		for _root, _dirs, _files in os.walk(library):
			if self.stopEv.is_set(): raise StopThreadEvent
			if not args['directory']:
				if (_root == library): continue

			if tscan and getMTime(_root) < tscan:
				_dirs[:] = []
				_files[:] = []

			_rootid = hashlib.md5(_root.encode('utf-8')).hexdigest()
			_audiodir = False
			_audiofile = None
			_validcoverimg = False
			_candidateimgs = []
			_coverfile = ''
			_mtime = int(time.time()) # fallback

			for file in _files:
				# tbd: following is rather convoluted > more precise logic needed
				_test = file.lower()
				if not _audiodir and isAudioFile(_test): _audiodir = True
				# check one file for embedded cover art
				if _audiodir and not _audiofile: _audiofile = file
				# valid cover image available?
				if isCoverFile(file): _validcoverimg = True
				# candidate image for symlinking available?
				if isImageFile(_test) and isValidImage(os.path.join(_root, file)):
					_candidateimgs.append(file)
				# end FOR

			if not _audiodir or _validcoverimg: continue
			# dir mod time before any modification
			_mtime = store[_rootid]['mtime'] if (_rootid in store) else getMTime(_root)

			# ambience: go down (1)
			for dir in _dirs:
				_cwd = os.path.join(_root, dir)
				for file in os.listdir(_cwd):
					_test = file.lower()
					if isImageFile(_test) and isValidImage(os.path.join(_cwd, file)):
						_candidateimgs.append(os.path.join('.', dir, file))
			# ambience: go up (?)
			if not args['directory']:
				_poneup = os.path.abspath(os.path.join(_root, os.pardir))
				_ptwoup = os.path.abspath(os.path.join(_poneup, os.pardir))

				try: _distoneup = tree[hashlib.md5(_poneup.encode('utf-8')).hexdigest()]
				except: _distoneup = 0
				try: _disttwoup = tree[hashlib.md5(_ptwoup.encode('utf-8')).hexdigest()]
				except: _disttwoup = 0

				# implements a silly custom walk; use os.walk() instead?
				if _disttwoup > _distoneup:
					for fn in os.listdir(_poneup):
						file = os.path.join(_poneup, fn)
						if os.path.isfile(file):
							_test = fn.lower()
							if isImageFile(_test) and isValidImage(file):
								_candidateimgs.append(os.path.join('..', fn))
						elif (os.path.isdir(file) and fn != PurePath(_root).name):
							for _file in os.listdir(file):
								_test = _file.lower()
								if isImageFile(_test) and isValidImage(os.path.join(file, _file)):
									_candidateimgs.append(os.path.join('..', fn, _file))
				# end IF

			# first choice: symlink existing
			# tag extract is used as fallback option in interactive mode
			if len(_candidateimgs):
				store[_rootid] = {
					'mtime': _mtime,
					'path': _root,
					'img': _candidateimgs
				}
				printl("symlink candidate\t%s" % (_root,))
				continue
			# second choice: extract tag embedded cover
			if _audiofile and extractEmbedded(_root, _audiofile, _mtime): continue
			# third choice: task sacad
			if not _root in dirs:
				dirs.append(_root)
				# store the mod times as well
				store[_rootid] = {
					'mtime': _mtime,
					'path': _root
				}
			# end main scan :: os.walk()

		# sacad wrapper
		if not args['quick']:
			# recursion pre-work: remove irrelevant ancestors
			# not the most elegant solution
			udirs = []
			for _d in dirs:
				_u = True
				for dir in dirs:
					if (_d == dir): continue
					if Path(dir).is_relative_to(_d):
						_u = False
						break
				if _u: udirs.append(_d)

			dircnt = len(udirs)
			i = 0
			# process 10 cover images, then wait a bit
			batch = 0

			for dir in udirs:
				if self.stopEv.is_set(): raise StopThreadEvent
				try:
					_id = hashlib.md5(dir.encode('utf-8')).hexdigest()
					_mtime = store[_id]['mtime']
				except:
					printl("fatal: get properties failed at\t%s" % (dir,))
					_exit(1)
				_of = 'folder.jpg' if args['magnetic'] else os.path.join(_.cfg.TMP, "%s.jpg" % (_id,))
				# target file exists
				if os.path.isfile(_of):
					# set the marker to resume in interactive mode
					if not args['magnetic']: store[_id]['img_unsafe'] = True
					continue

				i += 1
				print("%s of %s\t| processing.." % (i, dircnt))
				try:
					os.chdir(dir)
				except:
					printl("fatal: change dir failed at\t%s" % (dir,))
					_exit(1)
				# safety check
				if os.path.isfile('folder.jpg'): continue
				# log attempt
				if lf is not None: lf.write("\nsacad_r called\t%s" % (dir, ))
				# get art via sacad
				if batch >= 10:
					print('Sleeping...')
					time.sleep(120)
					batch = 0

				p = subprocess.Popen([_.cfg.BIN['sacad_r'],
						'-t', '58',
						'--disable-low-quality-sources',
						'.',
						str(_.cfg.IMG['size']),
						_of
					],
					stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
				)
				p.wait()
				# Searching covers: 100%... 1/1 [00:55<00:00, 55.15s/cover, ok=1, errors=0, no result found=0]
				# simply check for a new file
				if os.path.isfile(_of):
					printl("cover fetched\t\t%s" % (dir,))
					if args['magnetic']: unTouch(dir, _mtime)
					else: store[_id]['img_unsafe'] = True
				else:
					printl("failed fetching cover\t%s" % (dir,))
				batch = batch+1
			# end FOR
		# end IF
		print("jobs finished")
	# end SCAN::run()
# end SCAN()

def _exit(code, ro=False):
	global lf
	if not ro:
		# dump store
		try:
			with io.open(_.cfg.STORE, 'w', encoding='utf8') as mf:
				json.dump(store, mf, ensure_ascii=False)
		except: pass
		# close the log
		if lf is not None:
			try: lf.write("\n")
			except: pass
			try: lf.close()
			except: pass
	sys.exit(code)

def clear():
	_ = subprocess.call('clear' if os.name =='posix' else 'cls')

def printl(str):
	global lf
	print(str)
	if lf is not None: lf.write(u"\n%s" % (str,))

def isValidImage(fn):
	lq = False
	try:
		im = Image.open(fn)
		im.verify()
		w, h = im.size
		if w < _.cfg.IMG['size_min']:
			lq = True
		# don't divide by zero
		elif (not w or not h):
			lq = True
		# update: editor includes all; may refine this later
		# needs to be square-ish
		#elif ((max(w, h) / min(w, h)) > 1.5):
		#	lq = True
		im.close()
		im = Image.open(fn)
		im.transpose(PIL.Image.FLIP_LEFT_RIGHT)
		im.close()
	except:
		return False
	if lq: return False
	return True

def unTouch(path, tstamp):
	os.utime(path, (int(time.time()), tstamp + _.cfg.RESTORE['increment']))

def getMTime(_root):
	(_mode, _ino, _dev, _nlink, _uid, _gid, _size, _atime, _mtime, _ctime) = os.stat(_root)
	return _mtime

# consider doing asc sort first before calling this
def imgSort(item1, item2):
	_l = ['cover', 'front', '_f', 'side a', 'a side']
	if any(_e in item1.lower() for _e in _l): return -1
	if any(_e in item2.lower() for _e in _l): return 1
	return 0

# prefer working/sub dir
def imgSort2(item1, item2):
	if item1.startswith('../'): return 1
	if item2.startswith('../'): return -1
	return 0

def yieldAudioFile(path):
	try:
		for f in os.listdir(path):
			if isAudioFile(f.lower()):
				return f
	except: pass
	return None

# lower() input assumed
def isAudioFile(f):
	if	f.endswith( '.mp3') or \
		f.endswith('.flac') or \
		f.endswith( '.ape') or \
		f.endswith( '.ogg') or \
		f.endswith('.opus') or \
		f.endswith(  '.wv') or \
		f.endswith( '.mp4'):
			return True
	return False

# lower() input assumed
def isImageFile(f):
	if	f.endswith( '.png') or \
		f.endswith( '.jpg') or \
		f.endswith('.jpeg'):
			return True
	return False

def searchCoverFile(path):
	try:
		for f in os.listdir(path):
			if isCoverFile(f): return True
	except: pass
	return False

def isCoverFile(f):
	if f.lower() in CoverFile.test: return True
	return False

# instead of calling this multiple times consider using a decorator
def buildCoverTest():
	if hasattr(CoverFile, 'built'): return
	CoverFile.ext = ['jpg', 'jpeg', 'png']
	CoverFile.name = ['cover', 'folder', 'album', 'albumart', 'front']
	CoverFile.test = []
	for name in CoverFile.name:
		for ext in CoverFile.ext:
			CoverFile.test.append("%s.%s" % (name, ext))
	CoverFile.built = True

# deal with input. this typically feeds a loop
def _input(_str):
	_in = input(_str)
	# direct image download
	if fetchImageByUrl.isValidURL(_in):
		return 4, ''
	# image editing
	elif 'm' in _in.lower():
		return 3, _str
	# affirmative
	elif 'y' in _in.lower():
		return 1, ''
	# explore
	elif 'e' in _in.lower():
		return -1, "\n> "
	# back
	elif 'b' in _in.lower():
		return 2, _str
	# first
	elif 'f' in _in.lower():
		return 5, _str
	# last
	elif 'l' in _in.lower():
		return 6, _str
	# extract (attempt)
	elif 'x' in _in.lower():
		return -2, "\n> "
	# negative
	else:
		return 0, ''

def extractEmbedded(_root, _audiofile, _mtime):
	_audiofile = os.path.join(_root, _audiofile)
	_coverfile = os.path.join(_.cfg.TMP, "%s.jpg" % (hashlib.md5(_audiofile.encode('utf-8')).hexdigest(),))
	# purge failrun leftover
	if os.path.isfile(_coverfile): os.remove(_coverfile)
	p = subprocess.Popen([_.cfg.BIN['ffmpeg'],
		'-hide_banner',
		'-loglevel',
		'quiet',
		'-i',
		_audiofile,
		'-c:v',
		'copy',
		_coverfile
	])
	p.wait()
	if os.path.isfile(_coverfile):
		_type = filetype.guess(_coverfile)
		if _type is not None:
			# tbd: add error checks to file ops (re_move)
			if (_type.extension == 'jpg' or _type.extension == 'jpeg'):
				p = subprocess.Popen([_.cfg.BIN['jpegoptim'], '-q', '--strip-all', _coverfile],
					stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
				)
				p.wait()
			elif (_type.extension == 'png'):
				_coverfileextf = _coverfile.replace(".jpg", ".png")
				os.rename(_coverfile, _coverfileextf)
				_coverfile = _coverfileextf
				p = subprocess.Popen([_.cfg.BIN['optipng'], 'quiet', 'o1', _coverfile],
					stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
				)
				p.wait()
			else: # not interested in exotic stuff (for now)
				os.remove(_coverfile)

			if not isValidImage(_coverfile):
				if os.path.isfile(_coverfile): os.remove(_coverfile)
			else:
				# processing done; move to final destination
				_coverfileDest = os.path.join(_root, "folder.%s" % (_type.extension,))
				# final check
				if os.path.isfile(_coverfileDest):
					printl("notice: cover target exists, not replacing\t%s" % (_coverfileDest,))
				else:
					shutil.move(_coverfile, _coverfileDest)
					unTouch(_root, _mtime)
					if not args['interactive']:
						store[hashlib.md5(_root.encode('utf-8')).hexdigest()] = {
							'mtime': _mtime,
							'path': _root
						}
					printl("cover extracted\t\t%s" % (_root,))
				return True
		# end IF
	# end IF
	return False
# end extractEmbedded()

def goInteractive():
	if not os.path.isfile(_.cfg.STORE):
		print(colored("fatal: file does not exist\t%s" % (_.cfg.STORE,), 'red'))
		_exit(1, True)
	with io.open(_.cfg.STORE, 'r', encoding='utf8') as mf:
		mfdata = mf.read()
	obj = json.loads(mfdata)
	cnt = len(obj)
	for _ix, _id in enumerate(obj):
		if not os.path.isdir(obj[_id]['path']): continue
		# reduce spam in case user edited meanwhile
		if searchCoverFile(obj[_id]['path']): continue
		try:
			os.chdir(obj[_id]['path'])
		except:
			print(colored("error: change dir failed", 'red'))
			continue
		if (not 'img' in obj[_id] and not 'img_unsafe' in obj[_id]):
			com.chat('sig=iter'.encode('utf-8'))
			print("%s\t%s" % (colored('notice: no candidate image for', 'cyan'), colored(obj[_id]['path'], 'magenta')))
			if not args['interactivist']: continue
			_feed = "\t\t\t\tType %s to open target folder.\n\t\t\t\tInput %s to fetch.\n~%s tasks remaining.\n> " % (colored('e[xplore]', 'green'), colored('<url>', 'yellow'), (cnt - _ix))
			while 1:
				_code, _feed = _input(_feed)
				if _code == -1:
					com.chat(("dir=%s" % (obj[_id]['path'],)).encode('utf-8'))
				elif _code == 4:
					if not fetchImageByUrl.get():
						print(colored("error: fetch image failed", 'red'))
					else:
						_code = 1
						clear()
						break
				else:
					clear()
					break
			# end WHILE
			if _code == 1: continue
		if 'img_unsafe' in obj[_id]:
			_if = os.path.join(_.cfg.TMP, "%s.jpg" % (_id,))
			_of = 'folder.jpg'
			if not os.path.isfile(_if): continue
			if os.path.isfile(_of):
				clear()
				continue
			print("%s\n%s" % (colored(obj[_id]['path'], 'magenta'), colored(_if, 'yellow')))
			if _.cfg.HELP_PREF_NET:
				with open(_if, mode='rb') as f: com.chat(f.read())
			else:
				com.chat(("id=%s" % (_id,)).encode('utf-8'))
			_feed = "Use as folder image?\t\tType %s to confirm.\n\t\t\t\tType %s to open target folder.\n\t\t\t\tInput %s to fetch.\n~%s tasks remaining.\n> " % (colored('y[es]', 'yellow'), colored('e[xplore]', 'green'), colored('<url>', 'yellow'), (cnt - _ix))
			while 1:
				_code, _feed = _input(_feed)
				if _code == -1:
					com.chat(("dir=%s" % (obj[_id]['path'],)).encode('utf-8'))
				elif _code == 1:
					shutil.move(_if, _of)
					clear()
					break
				elif _code == 4:
					if not fetchImageByUrl.get():
						print(colored("error: fetch image failed", 'red'))
					else:
						_code = 1
						clear()
						break
				elif _code == 0:
					os.remove(_if)
					clear()
					break
			# end WHILE
			if _code == 1: continue
		# end IF
		if not 'img' in obj[_id]: continue
		(obj[_id]['img']).sort(key=functools.cmp_to_key(imgSort))
		(obj[_id]['img']).sort(key=functools.cmp_to_key(imgSort2))
		_imgxl = len(obj[_id]['img']) - 1
		_imgx = -1
		while _imgx < _imgxl:
			_imgx += 1
			_if = os.path.join(obj[_id]['path'], obj[_id]['img'][_imgx])
			if not os.path.isfile(_if): continue
			_type = filetype.guess(_if)
			if _type is not None:
				if (_type.extension == 'jpg' or _type.extension == 'jpeg'): pass
				elif (_type.extension == 'png'): pass
				else:
					print(colored("error: unsupported image file type: %s" % (_if,), 'red'))
					continue
			else:
				print(colored("error: corrupt image file: %s" % (_if,), 'red'))
				continue
			_of = "folder.%s" % (_type.extension,)
			_cx = len(obj[_id]['path'])
			print(colored(_if[0:_cx], 'magenta') + colored(_if[_cx:], 'yellow'))
			if os.path.isfile(_of):
				# print(colored("notice: target file exists", 'cyan'))
				clear()
				break
			if _.cfg.HELP_PREF_NET:
				with open(os.path.join(obj[_id]['path'], obj[_id]['img'][_imgx]), mode='rb') as f: com.chat(f.read())
			else:
				com.chat(("file=%s" % (os.path.join(obj[_id]['path'], obj[_id]['img'][_imgx]),)).encode('utf-8'))
			_curr  = "(%s/%s)" % (_imgx + 1, _imgxl + 1)
			_more  = colored('no', 'cyan') if not (_imgxl - _imgx) else colored(_imgxl - _imgx, 'blue')
			_prev  = '' if not _imgx else "\n\t\t\t\tType %s to go to previous image." % (colored('b[ack]', 'red'),)
			_first = '' if _imgx < 2 else "\n\t\t\t\tType %s to go to first image." % (colored('f[irst]', 'red'),)
			_last  = '' if not _imgxl else "\n\t\t\t\tType %s to go to last image." % (colored('l[ast]', 'red'),)
			_expl  = "\n\t\t\t\tType %s to open target folder." % (colored('e[xplore]', 'green'),)
			_extr  = "\n\t\t\t\tType %s to poll embedded in tags." % (colored('x[tract]', 'yellow'),)
			_edit  = "\n\t\t\t\tType %s to edit image." % (colored('m[anipulate]', 'green'),)
			_url   = "\n\t\t\t\tInput %s to fetch." % (colored('<url>', 'yellow'),)
			_feed  = "Symlink folder image %s?\tType %s to confirm. Have %s more candidate images.%s%s%s%s%s%s%s\n~%s tasks remaining.\n> " % (_curr, colored('y[es]', 'yellow'), _more, _prev, _first, _last, _expl, _extr, _edit, _url, (cnt - _ix))
			while 1:
				_code, _feed = _input(_feed)
				if _code == 3:
					ie = ImageEditor(os.path.join(obj[_id]['path'], obj[_id]['img'][_imgx]))
					if _im := ie.feed():
						try:
							shutil.move(_im, 'folder.jpg')
						except:
							print(colored("fatal: move failed", 'red'))
							_exit(1, True)
						else:
							clear()
						break
				elif _code == 4:
					if not fetchImageByUrl.get():
						print(colored("error: fetch image failed", 'red'))
					else:
						_code = 1
						clear()
						break
				elif _code == -1:
					com.chat(("dir=%s" % (obj[_id]['path'],)).encode('utf-8'))
				elif _code == -2:
					if _audiofile := yieldAudioFile(obj[_id]['path']):
						if extractEmbedded(obj[_id]['path'], _audiofile, getMTime(obj[_id]['path'])):
							clear()
							break
					print(colored("notice: extract not successful", 'cyan'))
				elif _code == 1:
					try:
						os.symlink(obj[_id]['img'][_imgx], _of)
					except:
						print(colored("fatal: symlink failed", 'red'))
						_exit(1, True)
					else:
						clear()
					break
				elif (_code == 2 and _imgx):
					_imgx -= 2
					clear()
					break
				elif (_code == 5 and _imgx):
					_imgx = -1
					clear()
					break
				elif (_code == 6):
					_imgx = _imgxl - 1
					clear()
					break
				elif _code == 0:
					clear()
					break
			# end WHILE
			if _code == 1: break
			if (_code == 0 and searchCoverFile(obj[_id]['path'])): break
		# end WHILE
		# i.e. all symlink candidates declined
		if searchCoverFile(obj[_id]['path']): continue
		if _audiofile := yieldAudioFile(obj[_id]['path']):
			if extractEmbedded(obj[_id]['path'], _audiofile, getMTime(obj[_id]['path'])):
				# status printed in function
				# tbd: sacad fetch as next fallback (prompt for that?)
				continue
		# see above for unsupported or corrupt image continuation
		# tbd: remove dupe code
		if args['interactivist']:
			print(colored(obj[_id]['path'], 'magenta'))
			_feed = "\t\t\t\tType %s to open target folder.\n\t\t\t\tInput %s to fetch.\n~%s tasks remaining.\n> " % (colored('e[xplore]', 'green'), colored('<url>', 'yellow'), (cnt - _ix))
			while 1:
				_code, _feed = _input(_feed)
				if _code == -1:
					com.chat(("dir=%s" % (obj[_id]['path'],)).encode('utf-8'))
				elif _code == 4:
					if not fetchImageByUrl.get():
						print(colored("error: fetch image failed", 'red'))
					else:
						_code = 1
						clear()
						break
				else:
					clear()
					break
			# end WHILE
			if _code == 1: continue
	# end FOR
	print("interactive mode finished")
# end goInteractive()

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Semiautomatic Cover Art Dispatcher')
	parser.add_argument('-v', '--version', action='version', version='0.2.0')
	parser.add_argument('--tlsgenkeys', help='Produce certificates and keys for secure socket communication.',
		action='store_true', required=False
	)
	parser.add_argument('-C', '--clean', help='Remove log and json files.',
		action='store_const', const=True, default=False
	)
	parser.add_argument('-c', '--cleaner', help='Remove log and json files, and all temporary files.',
		action='store_const', const=True, default=False
	)
	parser.add_argument('-r', '--restore', help='Restore folder modification times.',
		action='store_const', const=True, default=False
	)
	parser.add_argument('-I', '--interactive', help='Interactive mode, for symlinks and fetched images.',
		action='store_true', required=False
	)
	parser.add_argument('-i', '--interactivist', help='Prompt any (empty) in interactive mode.',
		action='store_true', required=False
	)
	parser.add_argument('-m', '--magnetic', help='Directly put sacad images in target folder during scan (not recommended).',
		action='store_true', required=False
	)
	parser.add_argument('-q', '--quick', help='Skip sacad fetch during scan.',
		action='store_true', required=False
	)
	parser.add_argument('-s', '--signal', help='Signal clients: ping | kill', required=False)

	parser.add_argument('-l', '--library', help='Library scan. Provide path to root directory.', required=False)
	parser.add_argument('-L', '--recentlib', help="Exclude modified before %s" % (datetime.datetime.fromtimestamp(int(time.time()) - _.cfg.TSCAN).strftime('%Y-%m-%d'),), required=False)
	parser.add_argument('-d', '--directory', help='Folder scan. Provide path to directory.', required=False)
	parser.add_argument('-D', '--recentdir', help="Exclude modified before %s" % (datetime.datetime.fromtimestamp(int(time.time()) - _.cfg.TSCAN).strftime('%Y-%m-%d'),), required=False)
	args = vars(parser.parse_args())

	_sd = os.path.dirname(os.path.realpath(__file__))
	if not _.cfg.LOG: _.cfg.LOG = os.path.join(_sd, 'sacad_w.log')
	if not _.cfg.STORE: _.cfg.STORE = os.path.join(_sd, 'sacad_w.json')
	if not _.cfg.TMP: _.cfg.TMP = os.path.join(_sd, 'tmp')

	if _exe := shutil.which("sacad_r"): _.cfg.BIN['sacad_r'] = _exe
	if _exe := shutil.which("ffmpeg"): _.cfg.BIN['ffmpeg'] = _exe
	if _exe := shutil.which("optipng"): _.cfg.BIN['optipng'] = _exe
	if _exe := shutil.which("jpegoptim"): _.cfg.BIN['jpegoptim'] = _exe
	if _exe := shutil.which("curl"): _.cfg.BIN['curl'] = _exe
	if _exe := shutil.which("openssl"): _.cfg.BIN['openssl'] = _exe
	if _exe := shutil.which("cat"): _.cfg.BIN['cat'] = _exe

	if (args['interactivist'] or args['signal'] or args['tlsgenkeys']): args['interactive'] = True
	if args['cleaner']: args['clean'] = True
	if args['directory']: args['library'] = args['directory']

	if args['recentlib']:
		args['library'] = args['recentlib']
		tscan = int(time.time()) - _.cfg.TSCAN
	elif args['recentdir']:
		args['library'] = args['recentdir']
		tscan = int(time.time()) - _.cfg.TSCAN
	else:
		tscan = None

	if args['restore']:
		if not os.path.isfile(_.cfg.STORE):
			print(colored("fatal: file does not exist\t%s" % (_.cfg.STORE,), 'red'))
			_exit(1, True)
		with io.open(_.cfg.STORE, 'r', encoding='utf8') as mf:
			mfdata = mf.read()
		obj = json.loads(mfdata)
		for _id in obj:
			if not os.path.isdir(obj[_id]['path']):
				print(colored("error: directory not found\t" % (obj[_id]['path'],), 'red'))
				continue
			unTouch(obj[_id]['path'], obj[_id]['mtime'])
		print("restore finished")

	if args['clean']:
		try:
			if os.path.isfile(_.cfg.LOG): os.remove(_.cfg.LOG)
			if os.path.isfile(_.cfg.STORE): os.remove(_.cfg.STORE)
			if args['cleaner']:
				for _fn in os.listdir(_.cfg.TMP):
					_f = os.path.join(_.cfg.TMP, _fn)
					if os.path.isfile(_f): os.remove(_f)
		except Exception as e:
			print(colored(f"fatal: clean: {e}", 'red'))
			_exit(1, True)
		finally:
			print("clean finished")

	if args['interactive']:
		# helper: review artwork
		# addr: <str> or None to skip
		# port: <int> or None to skip
		hv_addr = None
		hv_port = None
		# helper: explore
		he_addr = None
		he_port = None
		# tbd: validation
		for _ip in _.cfg.HELP_CLIENTS:
			if _.cfg.HELP_CLIENTS[_ip]['IS_VIEWER']:
				hv_addr = _ip
				hv_port = _.cfg.HELP_CLIENTS[_ip]['BIND_PORT']
			if _.cfg.HELP_CLIENTS[_ip]['IS_EXPLORER']:
				he_addr = _ip
				he_port = _.cfg.HELP_CLIENTS[_ip]['BIND_PORT']

		com = COM()

		if args['tlsgenkeys']:
			com.genSSLKeys()
			_exit(0, True)

		if (args['signal']):
			if 'kill' in args['signal'].lower():
				com.chat('sig=kill'.encode('utf-8'))
				_exit(0, True)
			if 'ping' in args['signal'].lower():
				com.chat('sig=ping'.encode('utf-8'))
				_exit(0, True)

		try:
			buildCoverTest()
			fetchImageByUrl = FetchImageURL()
			goInteractive()
		except KeyboardInterrupt:
			print("Shut down on SIGINT")
		except Exception as e:
			print(f"Shut down on RUNTIME_ERROR: {e}\n{traceback.format_exc()}")
		finally:
			com.chat('sig=int'.encode('utf-8'))

	if args['library']:
		if not os.path.isdir(args['library']):
			mapper = Mapper(args['library'])
			args['library'] = mapper.map()
			if not os.path.isdir(args['library']):
				print(colored("error: invalid folder/library: %s\nusage: sacad_w.py -d <path>" % (args['library'],), 'red'))
				_exit(1, True)
		library = os.path.normpath(args['library'])
		if _.cfg.LOL: lf = io.open(_.cfg.LOG, 'a', encoding='utf8')
		try:
			buildCoverTest()
			scan = Scan()
			scan.daemon = True
			scan.start()
			while 1:
				if not scan.is_alive(): break
				time.sleep(0.3)
		except KeyboardInterrupt:
			print("Shut down on SIGINT")
		except Exception as e:
			print(f"Shut down on RUNTIME_ERROR: {e}\n{traceback.format_exc()}")
		finally:
			if (scan is not None and scan.is_alive()):
				try:
					scan.stop()
					i = 0
					while scan.is_alive():
						i += 1
						if i > 20: break
						time.sleep(0.5)
				except: pass
			_exit(0)

	_exit(0, True)

