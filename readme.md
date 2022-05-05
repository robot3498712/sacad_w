# sacad_w

## Semiautomatic Cover Art Dispatcher / Wrapper


### Dependencies & preconditions

* Python >= 3.9 (server) | Python 3 (helper)
	* server intended to run on *nix, helper on windows
* See _config.py


### Purpose / usage / notes

See sacad_w.py. In a nutshell, you have a LOT of cover images to fix, and prefer not pulling all your hair out.

* Edit _config.py to get started.
* sacad_w.py -h, launch helper(s), setup TLS and then scan your library.

This isn't very polished, quickly made to work for my niche use case with incremental tweaks.