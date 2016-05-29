#!/usr/bin/env python
from __future__ import print_function
import sys, portage, re, subprocess, os
import solver, random, requests
from subprocess import PIPE, Popen

# Save a reference to the portage tree
try:
    db = portage.db[portage.root]["porttree"].dbapi
except KeyError:
    db = portage.db[portage.root]["vartree"].dbapi

# Query active USE flags for current environment
use = portage.settings["USE"].split()

# Keep a list of the packages that have now been stabilized
stabilized = []

# This functions returns the absolute value of the flag
# thus -X would return X and X will also return X
def abs_flag(flag):
    if flag[0] == '-':
        return flag[1:]
    return flag

# For a given token, and a combination of USE flags,
# This function retrieves the dependencies (highest
# version possible) and returns
def dep_resolve(cpv, combo):
    # Create a copy of the environment
    my_env = os.environ.copy()

    # Add ~amd64 to the keywords ( to get the latest package )
    if "ACCEPT_KEYWORDS" in my_env: my_env["ACCEPT_KEYWORDS"] += " ~amd64"
    else: my_env["ACCEPT_KEYWORDS"] = "~amd64"

    # Add the USE combination to the existing USE flags. Add to
    # the end so that they would override the existing flags
    if "USE" in my_env: my_env["USE"] += " ".join(combo)
    else: my_env["ACCEPT_KEYWORDS"] = portage.settings["USE"] + " " + " ".join(combo)

    # Let portage solve the build tree to find the best compatible
    # dependencies (highest possible version)
    args = ['emerge', '--pretend', "="+cpv]
    process = Popen(args, env=my_env, stdout=PIPE, stderr=PIPE)
    deps = []
    for line in process.stdout:
        line = line.decode(encoding='UTF-8')

        # Retrieve the lines that show dependencies present
        # and append the required token to the dependency list
        dep = re.findall('^\[ebuild.*\]\s*([^\s]+)', line)
        if dep:
            deps.append(dep[0])
    return (deps, my_env)

# For given use flags and required use combination
# It uses random methods to generate valid yet random
# combinations of USE flags to build/test the package
def get_use_combinations(use_flags, req_use):
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

    # Sort all combinations on the number of enabled USE flags
    for i, soln in enumerate(req_solns):
        req_solns[i] = (sum(1 for k in soln if k[0] != '-'), soln)
    req_solns.sort(key=lambda tup:tup[0])

    # use_flags are those that weren't in req_flags, thus both
    # sets are now mutually exclusive
    req_flags = set(req_flags)
    use_flags = set(use_flags) - req_flags

    # Combination number one: Minimum possible USE flags enabled
    tmp_use = ["-"+k for k in use_flags] + req_solns[0][1]
    final_combinations.append(tmp_use)

    # Combination number two: Maximum possible USE flags enabled
    tmp_use = [k for k in use_flags] + req_solns[-1][1]
    final_combinations.append(tmp_use)

    # Combination number three: Random + Random
    bias = random.randrange(0,10) # Number between 0 and 9
    tmp_use = [("-" if random.randrange(0,10) <= bias else "") + k for k in use_flags]
    tmp_use += req_solns[random.randrange(0, len(req_solns))][1]
    final_combinations.append(tmp_use)

    # Combination number three: Random + Random
    bias = random.randrange(0,10) # Number between 0 and 9
    tmp_use = [("-" if random.randrange(0,10) <= bias else "") + k for k in use_flags]
    tmp_use += req_solns[random.randrange(0, len(req_solns))][1]
    final_combinations.append(tmp_use)

    # Remove repeated sets by using a set of sets
    return set(frozenset(k) for k in final_combinations)

# This is the main controller function for the stabilization script.
# Any package to be stabilized has to be passed to this function
def stabilize(cpv):
    print("Now stabilizing,", cpv)

    # Retrieve the USE and REQUIRED_USE flags from the portage API
    use_flags, req_use = db.aux_get(cpv, ["USE", "REQUIRED_USE"])

    # Returns a few valid USE flag combinations to test the build
    combos = get_use_combinations(use_flags, req_use)

    # For every combination, find the dependencies, recursively run
    # their stabilizations, and then finally build this token to see
    # if it succeeds.
    for i, use_combo in enumerate( combos ):
        print("Trial number:", i, "for the following USE flag combination:", use_combo)
        ret_deps, my_env = dep_resolve(cpv, use_combo)
        print("Current package", cpv, "has the following dependencies:")
        print("\n".join(ret_deps))
        deps = [ k for k in ret_deps if k != cpv ]
        for dep_cpv in deps:
            keywords = db.aux_get(dep_cpv, ["KEYWORDS"])[0].split()
            if '~amd64' in keywords and dep_cpv != cpv:
                print("Dependency", dep_cpv, "needs to be stabilized first.")
                ret_code = stabilize(dep_cpv)
                if ret_code != 0:
                    sys.stderr.write("Stabilization of one or more dependencies failed")
                    exit(0)
                else:
                    stabilized.append(cpv)
            else:
                print("Dependency", dep_cpv, "is already stable")
        args = ['emerge', '--autounmask-write', "="+cpv]
        unmask = Popen(args, env=my_env, stdout=PIPE, stderr=PIPE)
        retry = False
        for line in iter(unmask.stdout.readline, b""):
            print(line, end='')
            if 'Autounmask changes' in line:
               retry = True
        print("The return code was: ", unmask.returncode)
        if retry:
            yes = Popen(['yes'], stdout=PIPE)
            etc = Popen(['etc-update', '--automode', '-3'], stdin=yes.stdout,
                    stdout=PIPE)
            for line in iter(etc.stdout.readline, b""):
                print(line, end='')
            emm = Popen(['emerge', "="+cpv], stdout=PIPE)
            for line in iter(emm.stdout.readline, b""):
                print(line, end='')
            print("The return code was: ", emm.returncode)
    return 0

if __name__ == '__main__':
    package = sys.argv[1]
    try:
        token = db.xmatch("match-all", package)
    except portage.exception.InvalidAtom as e:
        sys.stderr.write("Error: Invalid token name: "+str(e).strip()+"\n")
        exit(1)
    except portage.exception.AmbiguousPackageName as e:
        sys.stderr.write("Error: Ambiguous token: "+str(e).strip()+"\n")
        exit(1)
    if token == []:
        sys.stderr.write("Error: No Package Found\n")
        exit(1)
    cpv = [k for k in token if '9999' not in k]
    if len(cpv) > 1:
        print("Multiple versions found, assuming latest version")
        cpv = cpv[-1]
    stabilize(cpv)
