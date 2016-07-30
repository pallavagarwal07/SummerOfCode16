#!/usr/bin/env python
from __future__ import print_function
import portage
import subprocess
import base64
import os
import re
import random
import requests
import sys
import socket
import time
import traceback
import helpers
import binascii
from subprocess import PIPE, Popen, check_output

print("Started container.py")

# This list will maintain a log of everything that happens
log = []

global uniq_code
global folder_name
uniq_code = ""

# Save a reference to the portage tree
try:
    db = portage.db[portage.root]["porttree"].dbapi
except KeyError:
    db = portage.db[portage.root]["vartree"].dbapi

# Query active USE flags for current environment
use = portage.settings["USE"].split()


def _exit(retcode):
    """
    This is a wrapper over the original exit function to ensure that the
    log files are written before the program exits
    """
    append_log("Container exited with a return code", retcode)
    exit(retcode)


def append_log(*args):
    """
    Function to append to file (emerge_logs)
    """
    args = " ".join([str(k) for k in args])
    args += "\n" if args[-1] != "\n" else ""
    with open(folder_name + "emerge_logs", "a") as f:
        os.chmod(folder_name + "emerge_logs", 0o666)
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


def dep_resolve(cpv, combo):
    """
    For a given token, and a combination of USE flags,
    This function retrieves the dependencies (highest
    version possible) and returns
    """

    # Create a copy of the environment
    my_env = os.environ.copy()

    # Add ~amd64 to the keywords ( to get the latest package )
    # if "ACCEPT_KEYWORDS" in my_env:
        # my_env["ACCEPT_KEYWORDS"] += " ~amd64"
    # else:
        # my_env["ACCEPT_KEYWORDS"] = "~amd64"

    # Add the USE combination to the existing USE flags. Add to
    # the end so that they would override the existing flags
    if "USE" in my_env:
        my_env["USE"] += " " + " ".join(combo)
    else:
        my_env["USE"] = portage.settings["USE"] + " " + " ".join(combo)

    #TODO Add to file corresponding to the particular package instead
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


if __name__ == "__main__":
    try:
        buf = requests.get('http://162.246.156.59:32000/request-package').text
        if buf == 'abort' or buf == 'None':
            _print("The server doesn't have a package to be stabilized yet.")
            _exit(0)

        print("Server sent the package", buf)
        cpv, use = buf.split("[;;]")

        global folder_name
        folder_name = "/root/build/"

        cpv = cpv.strip()
        assert cpv != None

        use_combo = use.strip()
        assert use_combo != None

        my_env = os.environ.copy()
        if "USE" in my_env:
            my_env["USE"] += " " + use_combo
        else:
            my_env["USE"] = portage.settings["USE"] + " " + use_combo
        my_env["USE"] += " test "

        args = ['emerge', '-UuD', '--autounmask-write', "--backtrack=50", "=" + cpv]
        unmask = Popen(args, env=my_env, stdout=PIPE, stderr=PIPE)

        # This boolean flag takes care of running the emerge command a second
        # time if the first run causes a change in config file changes due to
        # autounmask-write
        retry = False

        for line in iter(unmask.stdout.readline, b""):
            append_log(line)
            # If changes have been written to config files, then this condition
            # should return true. #TODO Find a better way to do this.
            if 'Autounmask changes' in line or re.search('needs? updating', line):
                retry = True
            if re.search(r'(keyword|USE) changes', line):
                retry = True
            line = line[:77] + re.sub('.', '.', line[77:80])
            print(line, end='')

        for line in iter(unmask.stderr.readline, b""):
            append_log(line)
            if 'Autounmask changes' in line or re.search('needs? updating', line):
                retry = True
            if re.search(r'(keyword|USE) changes', line):
                retry = True
            line = line[:77] + re.sub('.', '.', line[77:80])
            print(line, end='')

        unmask.wait()
        _print("The return code was: ", unmask.returncode)

        if retry:
            # Use etc-update to commit the automask changes to file
            yes = Popen(['yes'], stdout=PIPE)
            etc = Popen(['etc-update', '--automode', '-3'],
                        stdin=yes.stdout, stdout=PIPE, stderr=PIPE)

            # Save and log the output
            for line in iter(etc.stdout.readline, b""):
                append_log(line)
                line = line[:77] + re.sub('.', '.', line[77:80])
                print(line, end='')

            # Save and log the output
            for line in iter(etc.stderr.readline, b""):
                append_log(line)
                line = line[:77] + re.sub('.', '.', line[77:80])
                print(line, end='')
            etc.wait()
            yes.terminate()

            # Finally, run the build.
            emm = Popen(['emerge', '-UuD', "--backtrack=50", "=" + cpv], stdout=PIPE,
                        stderr=PIPE)
            for line in iter(emm.stdout.readline, b""):
                append_log(line)
                line = line[:77] + re.sub('.', '.', line[77:80])
                print(line, end=('' if line[-1] == '\n' else '\n'))

            for line in iter(emm.stderr.readline, b""):
                append_log(line)
                line = line[:77] + re.sub('.', '.', line[77:80])
                print(line, end=('' if line[-1] == '\n' else '\n'))

            # If return code != 0 (i.e. The build failed)
            if emm.wait() != 0:
                # Check to see if internet is working
                if helpers.internet_working:
                    _exit(emm.returncode)
                else:
                    _print("Sorry, but you seem to have an internet failure")
                    _exit(1)
        else:
            # Similarly for first case. If emerge failed, check if
            # internet is working. If yes, then report the error
            if unmask.returncode != 0:
                if helpers.internet_working:
                    _exit(unmask.returncode)
                else:
                    _print("Sorry, but you seem to have an internet failure")
                    _exit(1)
    except Exception as e:
        desired_trace = traceback.format_exc(sys.exc_info())
        append_log(desired_trace)
        _exit(1)
