#!/usr/bin/env python2
from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer
from base64 import urlsafe_b64decode as b64decode
from urlparse import urlparse
import os
import re
import sys
import thread
# import portage
import subprocess as sp

# sync_logs = sp.check_output(['emerge', '--sync'])
# """Save a reference to the portage tree"""
# try:
    # db = portage.db[portage.root]["porttree"].dbapi
# except KeyError:
    # db = portage.db[portage.root]["vartree"].dbapi

# """Query active USE flags for current environment"""
# use = portage.settings["USE"].split()

PORT_NUMBER = 7071


def split_up(cpv):
    """
    Output the details for the rest of the containers
    """

    # Retrieve the USE and REQUIRED_USE flags from the portage API
    use_flags, req_use = db.aux_get(cpv, ["IUSE", "REQUIRED_USE"])

    # Returns a few valid USE flag combinations to test the build
    combos = get_use_combinations(use_flags, req_use)
    combos = list(combos)
    total = len(combos)

    for i in range(total):
        payload = {'package': cpv, 'flags': " ".join(combos)}
        r = requests.get("http://localhost/add-combo", params=payload)
        assert r.text == "1"

        url = cpv + ";" + " ".join(combos)

        encodedURL = "http://localhost:7072/" + base64.b64encode(url)
        r2 = requests.get(encodedURL)
        assert r2.text == "Ok!"
    

def get_use_combinations(use_flags, req_use):
    """
    For given use flags and required use combination
    It uses random methods to generate valid yet random
    combinations of USE flags to build/test the package
    """

    # use_flags is a string by default
    use_flags = [k.replace('-', '').replace('+', '') for k in use_flags.split()]

    # List to store final generated USE flag combinations
    final_combinations = []

    # Absolute values of flags from the required use variable
    req_flags = []

    # Sat solver determines all valid combinations of req_use
    req_solns = solver.main(req_use)

    # Fill in req_flags from any of the solutions([] in case of
    # no req_use variable)
    for signed_flag in req_solns[0]:
        req_flags.append(abs_flag(signed_flag))

    # Sort all cmbinations on the number of enabled USE flags
    for i, soln in enumerate(req_solns):
        req_solns[i] = (sum(1 for k in soln if k[0] != '-'), soln)
    req_solns.sort(key=lambda tup: tup[0])

    # use_flags are those that weren't in req_flags, thus both
    # sets are now mutually exclusive
    req_flags = set(req_flags)
    use_flags = set(use_flags) - req_flags

    # Combination number one: Minimum possible USE flags enabled
    tmp_use = ["-" + k for k in use_flags] + req_solns[0][1]
    final_combinations.append(tmp_use)

    # Combination number two: Maximum possible USE flags enabled
    tmp_use = [k for k in use_flags] + req_solns[-1][1]
    final_combinations.append(tmp_use)

    # Combination number three: Random + Random
    bias = random.randrange(0, 10)  # Number between 0 and 9
    tmp_use = [("-" if random.randrange(0, 10) <=
                bias else "") + k for k in use_flags]
    tmp_use += req_solns[random.randrange(0, len(req_solns))][1]
    final_combinations.append(tmp_use)

    # Combination number three: Random + Random
    bias = random.randrange(0, 10)  # Number between 0 and 9
    tmp_use = [("-" if random.randrange(0, 10) <=
                bias else "") + k for k in use_flags]
    tmp_use += req_solns[random.randrange(0, len(req_solns))][1]
    final_combinations.append(tmp_use)

    # Remove repeated sets by using a set of sets
    return set(frozenset(k) for k in final_combinations)

def b64pad(msg):
    return msg+(4-len(msg)%4 if len(msg)%4!=0 else 0)*"="

class myHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type','text/html')
        self.end_headers()
        path = b64pad(self.path[1:])
        cpv = b64decode(path)
        thread.start_new_thread(split_up,(cpv,))
        self.wfile.write("Ok!")
        return
try:
    print ('Starting httpserver on port ' + str(i))
    sys.stdout.flush()
    server = HTTPServer(('', i), myHandler)
    print ('Started httpserver on port ' + str(i))
    sys.stdout.flush()
    server.serve_forever()
except KeyboardInterrupt:
    print ('^C received, shutting down the web server')
    sys.stdout.flush()
    server.socket.close()
