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
import time

global uniq_code

"""Save a reference to the portage tree"""
try:
    db = portage.db[portage.root]["porttree"].dbapi
except KeyError:
    db = portage.db[portage.root]["vartree"].dbapi

"""Query active USE flags for current environment"""
use = portage.settings["USE"].split()


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


def split_up(cpv):
    """
    Output the details for the rest of the containers
    """
    _print("Extracting information for", cpv)

    # Retrieve the USE and REQUIRED_USE flags from the portage API
    use_flags, req_use = db.aux_get(cpv, ["IUSE", "REQUIRED_USE"])

    # Returns a few valid USE flag combinations to test the build
    combos = get_use_combinations(use_flags, req_use)


def get_use_combinations(use_flags, req_use):
    """
    For given use flags and required use combination
    It uses random methods to generate valid yet random
    combinations of USE flags to build/test the package
    """

    # use_flags is a string by default
    use_flags = [k.replace('-', '').replace('+', '')
                 for k in use_flags.split()]

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
