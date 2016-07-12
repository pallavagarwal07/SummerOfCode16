#!/usr/bin/env python2
from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer
from base64 import urlsafe_b64decode as b64decode
from urlparse import urlparse
import os
import re
import sys
import thread
import portage
import subprocess as sp

# sync_logs = sp.check_output(['emerge', '--sync'])

"""Save a reference to the portage tree"""
try:
    db = portage.db[portage.root]["porttree"].dbapi
except KeyError:
    db = portage.db[portage.root]["vartree"].dbapi

"""Query active USE flags for current environment"""
use = portage.settings["USE"].split()

PORT_NUMBER = 7072

def dep_resolve(cpv, combo):
    # Create a copy of the environment
    my_env = os.environ.copy()

    # Add ~amd64 to the keywords ( to get the latest package )
    if "ACCEPT_KEYWORDS" in my_env:
        my_env["ACCEPT_KEYWORDS"] += " ~amd64"
    else:
        my_env["ACCEPT_KEYWORDS"] = "~amd64"

    # Add the USE combination to the existing USE flags. Add to
    # the end so that they would override the existing flags
    if "USE" in my_env:
        my_env["USE"] += " " + combo
    else:
        my_env["USE"] = portage.settings["USE"] + " " + combo
    my_env["USE"] += " test "

    # Let portage solve the build tree to find the best compatible
    # dependencies (highest possible version)
    args = ['emerge', '-pUuD', "=" + cpv]
    process = Popen(args, env=my_env, stdout=PIPE, stderr=PIPE)
    deps = []
    for line in process.stdout:
        line = line.decode(encoding='UTF-8')

        # Retrieve the lines that show dependencies present
        # and append the required token to the dependency list
        dep = re.findall('^\[ebuild.*?\]\s*?([^\s]+)', line)
        if dep:
            deps.append(dep[0])
    return (deps, my_env)


def build_pretend(cpv, flags):
    deps, my_env = dep_resolve(cpv, flags)
    deps = [k for k in ret_deps if k != cpv]

    for dep_cpv in deps:
        keywords = db.aux_get(dep_cpv, ["KEYWORDS"])[0].split()

        # Check if the current status of the package is '~amd64' (Untested)
        if '~amd64' in keywords and dep_cpv != cpv:
            payload = {
                'parent': b64encode(cpv),
                'dependency': b64encode(dep_cpv)
            }

            # Check what the server has to say about the package.
            # The parent has to be sent too in case the package has
            # been marked "fake - stabilized"
            response = requests.get("http://localhost/sched-dep", params=payload)

            assert response.status_code == 200
        else:
            _print("Dependency", dep_cpv, "is already stable")


class myHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type','text/html')
        self.end_headers()
        path = b64pad(self.path[1:])
        cpv, flags = b64decode(path).split(";")
        thread.start_new_thread(build_pretend, (cpv, flags))
        self.wfile.write("Ok!")
        return
try:
    print 'Starting httpserver on port ', PORT_NUMBER
    sys.stdout.flush()
    server = HTTPServer(('', PORT_NUMBER), myHandler)
    print 'Started httpserver on port ' , PORT_NUMBER
    sys.stdout.flush()
    server.serve_forever()
except KeyboardInterrupt:
    print '^C received, shutting down the web server'
    sys.stdout.flush()
    server.socket.close()
