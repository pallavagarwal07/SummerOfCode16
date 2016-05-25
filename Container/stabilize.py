#!/usr/bin/env python
from __future__ import print_function
import sys, portage, re, subprocess, os
from subprocess import PIPE, Popen

# Save a reference to the portage tree
try:
    db = portage.db[portage.root]["porttree"].dbapi
except KeyError:
    db = portage.db[portage.root]["vartree"].dbapi
# Query active USE flags for current environment
use = portage.settings["USE"].split()
stabilized = []

def multi_build(cpv):


def dep_resolve(cpv):
    my_env = os.environ.copy()
    if "ACCEPT_KEYWORDS" in my_env: my_env["ACCEPT_KEYWORDS"] += "~amd64"
    else: my_env["ACCEPT_KEYWORDS"] = "~amd64"
    args = ['emerge', '--pretend', "="+cpv]
    process = Popen(args, env=my_env, stdout=PIPE, stderr=PIPE)
    deps = []
    for line in process.stdout:
        line = line.decode(encoding='UTF-8')
        dep = re.findall('^\[ebuild.*\]\s*([^\s]+)', line)
        if dep:
            deps.append(dep[0])
    return deps

def stabilize(cpv):
    deps = [ k for k in dep_resolve(cpv) if k != cpv ]
    for dep_cpv in deps:
        keywords = db.aux_get(dep_cpv, ["KEYWORDS"])[0].split()
        if '~amd64' in keywords and dep_cpv != cpv:
            ret_code = stabilize(dep_cpv)
            if ret_code != 0:
                sys.stderr.write("Stabilization of one or more dependencies failed")
                exit(0)
            else:
                stabilized.append(cpv)
    multi_build(cpv)
    return 0

if __name__ == '__main__':
    package = sys.argv[1]
    try:
        token = db.xmatch("match-all", package)
    except Exception as e:
        sys.stderr.write("Error: Ambiguous token: "+str(e).strip()+"\n")
        exit(1)
    if token == []:
        sys.stderr.write("Error: Invalid token\n")
        exit(1)
    cpv = [k for k in token if '9999' not in k]
    if len(cpv) > 1:
        print("Multiple versions found, assuming latest version")
        cpv = cpv[-1]
    stabilize(cpv)
