#!/usr/bin/env python
from __future__ import print_function
from subprocess import PIPE, Popen
import base64
import binascii
import os
import portage
import random
import re
import requests
import solver
import subprocess
import sys
import socket
import time
global uniq_code

"""Save a reference to the portage tree"""
try:
    db = portage.db[portage.root]["porttree"].dbapi
except KeyError:
    db = portage.db[portage.root]["vartree"].dbapi

"""Query active USE flags for current environment"""
use = portage.settings["USE"].split()

def _exit(n):
    """
    Custom exit function that uploads the logs before exiting
    """
    uploadLog()
    exit(n)

def append_log(*args):
    """
    Function to append to file (pretend_logs)
    """
    args = " ".join([str(k) for k in args])
    args += "\n" if args[-1] != "\n" else ""
    with open("pretend_logs", "a") as f:
        f.write(args)


def _print(*args):
    """
    Print to stdout, and log to file
    """
    append_log(*args)
    print(*args)


def eprint(*args, **kwargs):
    """
    Print function equivalent for stderr
    """
    print(*args, file=sys.stderr, **kwargs)


def _err(*args):
    """
    Print to stderr, and log to file
    """
    append_log(*args)
    eprint(*args)


def abs_flag(flag):
    """
    This functions returns the absolute value of the flag
    """
    if flag[0] == '-':
        return flag[1:]
    return flag


def b64encode(s):
    """
    Returns an unpadded version of url safe base64 encoded string
    """
    return base64.urlsafe_b64encode(s).replace('=', '')


def get_hash():
    """
    Create a random hashed id for this run
    """
    return str(binascii.hexlify(os.urandom(4)).decode("utf-8"))


if __name__ == '__main__':
    """
    Main function: Control mechanism that decides and outputs info for
    other dontainers to run on.
    """

    append_log("Command:", *sys.argv)

    global uniq_code
    uniq_code = get_hash()

    # If package is not specified, ask the server which package needs
    # to be stabilized
    if len(sys.argv) < 2:
        _print("No package specified. Asking the server for one")
        package_resp = requests.get("http://162.246.156.136/request-package")

        if package_resp.status_code != 200:
            _print("Stabilization server offline or unaccessible. Exiting")
            _exit(0)

        # Save whatever package name is returned from the server
        package = package_resp.text
        _print("Got package:", package)
    else:
        # If package name is specified, use that
        package = sys.argv[1]

    # The package name provided may not be a valid cpv. So, use the
    # portage API to find the most appropriate match
    try:
        token = db.xmatch("match-all", package)
    except portage.exception.InvalidAtom as e:
        _err("Error: Invalid token name:", str(e).strip())
        _exit(1)
    except portage.exception.AmbiguousPackageName as e:
        _err("Error: Ambiguous token: ", str(e).strip())
        _exit(1)

    append_log("Package:", package)

    if token == []:
        _err("Error: No Package Found")
        _exit(1)

    # Remove git versions. They are not to be stabilized (ever)
    cpv = [k for k in token if '9999' not in k]

    # Choose the latest unstabilized version
    if len(cpv) > 1:
        _print("Multiple versions found, assuming latest version")
    cpv = cpv[-1]

    # Try to stabilize the package and log the return code
    retcode = split_up(cpv)
    append_log("Retcode:", str(retcode))

    _exit(0)
