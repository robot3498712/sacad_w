'''
sacad_w :: config
'''

class Object(object): pass
cfg = Object()

# ---------------- server config

# log level: 0=OFF | 1=ON
cfg.LOL = 0

# (optional) <str>log_path - or relative to script dir
cfg.LOG = ''
# (optional) <str>store_path (json) -//-
cfg.STORE = ''
# (optional) <str>tmp_dir_path -//-
cfg.TMP = ''

# (optional) <str>bin_path - fallback for shutil.which()
cfg.BIN = {
	'sacad_r': '',
	'ffmpeg': '',
	'optipng': '',
	'jpegoptim': '',
	'curl': '',
	'openssl': '',
	'cat': ''
}

# <str>openssl key subject attributes
cfg.TLS_SUBJ = '/C=CH/ST=Appenzell/L=Innerrhoden/O=sacad_w/OU=sacad_w/CN='

# quality settings for image target
cfg.IMG = {
	'size': 600,
	'size_min': 250
}

# <int>increment - restore folder mod timestamp
# may be useful to catch updates on rescan
cfg.RESTORE = {
	'increment': 0
}

# <int>rescan offset in seconds
# exclude last modified before; for use with -L -D
cfg.TSCAN = 31104000

# ---------------- client config
# all paths: omit trailing slash
# if using network share be sure to escape slashes (use r'aw strings')

# tmp folder configured in sacad_w (where fetched cover art is stored)
cfg.HELP_TMP = r'\\MAPPED_DRIVE\data_folder'

# rewrite remote to local path; bi-directional lookup
cfg.HELP_MAP = {
	r'/home/library/Music': r'\\MAPPED_DRIVE\data_folder\Music',
	r'/home/library/Another-Music-Folder': r'\\MAPPED_DRIVE\data_folder\Another-Music-Folder',
}

# <bool>prefer networking for image previews
# if true send all files over socket; false to open preexisting shares locally
cfg.HELP_PREF_NET = False

# <list>ci word list to exclude from clipboard copy
cfg.HELP_CLIP_EXCL = ['flac', 'v0', '320', 'v2', 'ape', 'va', 'various']

# helper client dict
# bool values are relevant to the server
# CLIP, if true, issues clipboard copy on EXPLORER
cfg.HELP_CLIENTS = {
	'192.168.0.1': {
		'BIND_PORT': 33321,
		'IS_VIEWER': False,
		'IS_EXPLORER': True,
		'CLIP': True,
		'VIEWER_BIN': r'C:\Program Files (x86)\IrfanView\i_view32.exe',
		'TIMEOUT': 1
	},
	'192.168.0.2': {
		'BIND_PORT': 33321,
		'IS_VIEWER': True,
		'IS_EXPLORER': False,
		'CLIP': False,
		'VIEWER_BIN': r'C:\Program Files (x86)\IrfanView\i_view32.exe',
		'TIMEOUT': 1
	}
}
