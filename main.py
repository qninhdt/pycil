import sys, remote
from app import Pycil

if len(sys.argv) > 1:
    remote.user["name"] = sys.argv[1]

pycil = Pycil()
pycil.start()