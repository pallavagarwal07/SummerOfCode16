#!/usr/bin/env python
from __future__ import print_function
import portage, subprocess, base64, os, re
import solver, random, requests, sys, time
from subprocess import PIPE, Popen

log = []
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

def b64encode(s):
    return base64.urlsafe_b64encode(s).replace('=', '')

def uploadLog():
    log_txt = "\n".join(log)
    b64log = b64encode(log_txt)
    filename = time.strftime("%Y%m%d_%H%M%S")
    payload = {
                  'filename': filename,
                  'log': b64log
              }
    response = requests.get("http://162.246.156.136/submit-log",
            params=payload)

def _exit(n):
    uploadLog()
    exit(n)

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
    # use_flags is a string by default
    use_flags = [k.replace('-','').replace('+','') for k in use_flags.split()]

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
    use_flags, req_use = db.aux_get(cpv, ["IUSE", "REQUIRED_USE"])

    # Returns a few valid USE flag combinations to test the build
    combos = get_use_combinations(use_flags, req_use)

    # For every combination, find the dependencies, recursively run
    # their stabilizations, and then finally build this token to see
    # if it succeeds.
    for i, use_combo in enumerate(combos):

        print("Trial number:", i, "for the following USE flag combination:", use_combo)
        ret_deps, my_env = dep_resolve(cpv, use_combo)
        print("Current package", cpv, "has the following dependencies:")
        print("\n".join(ret_deps))

        continue_run = True
        deps = [ k for k in ret_deps if k != cpv ]
        for dep_cpv in deps:
            keywords = db.aux_get(dep_cpv, ["KEYWORDS"])[0].split()
            if '~amd64' in keywords and dep_cpv != cpv:
                print("Dependency", dep_cpv, "needs to be stabilized first.")
                payload = {
                            'parent'     : b64encode(cpv),
                            'dependency' : b64encode(dep_cpv)
                          }

                response = requests.get("http://162.246.156.136/sched-dep",
                                        params=payload)

                if response.status_code != 200:
                    print("Stabilization server offline or unaccessible. Exiting")
                    _exit(0)
                else:
                    if response.text == "0": # Has already been stabilized
                        pass
                    elif response.text == "1": # To be stabilized
                        continue_run = False
                    elif response.text == "3": # Should be blocked
                        with open("/etc/portage/package.mask/stabilizer", "a") as f:
                            f.write("\n="+dep_cpv)
                        continue_run = False
                    elif response.text == "-1":
                        print("Stabilization server returned error")
                        _exit(0)
            else:
                print("Dependency", dep_cpv, "is already stable")

        if not continue_run:
            return 999999

        args = ['emerge', '--autounmask-write', "--backtrack=50", "="+cpv]
        unmask = Popen(args, env=my_env, stdout=PIPE, stderr=PIPE)
        retry = False
        for line in iter(unmask.stdout.readline, b""):
            log.append(line)
            print(line, end='')
            if 'Autounmask changes' in line or re.search('needs? updating', line):
               retry = True
        unmask.wait()
        print("The return code was: ", unmask.returncode)

        if retry:
            yes = Popen(['yes'], stdout=PIPE)
            etc = Popen(['etc-update', '--automode', '-3'], stdin=yes.stdout,
                    stdout=PIPE )
            for line in iter(etc.stdout.readline, b""):
                log.append(line)
                print(line, end='')
            etc.wait()
            yes.terminate()
            emm = Popen(['emerge', "="+cpv], stdout=PIPE)
            for line in iter(emm.stdout.readline, b""):
                log.append(line)
                print(line, end='')
            if emm.wait() != 0:
                return emm.returncode
        else:
            if unmask.returncode != 0:
                return unmask.returncode
    return 0

if __name__ == '__main__':
    log.append("Command: " + " ".join(sys.argv))
    if len(sys.argv) < 2:
        print("No package specified. Asking the server for one")
        package_resp = requests.get("http://162.246.156.136/request-package")
        if package_resp.status_code != 200:
            print("Stabilization server offline or unaccessible. Exiting")
            _exit(0)
        package = package_resp.text
        print("Got package:", package)
    else:
        package = sys.argv[1]

    try:
        token = db.xmatch("match-all", package)
    except portage.exception.InvalidAtom as e:
        sys.stderr.write("Error: Invalid token name: "+str(e).strip()+"\n")
        _exit(1)
    except portage.exception.AmbiguousPackageName as e:
        sys.stderr.write("Error: Ambiguous token: "+str(e).strip()+"\n")
        _exit(1)

    log.append("Package: " + package)

    if token == []:
        sys.stderr.write("Error: No Package Found\n")
        _exit(1)
    cpv = [k for k in token if '9999' not in k]
    if len(cpv) > 1:
        print("Multiple versions found, assuming latest version")
    cpv = cpv[-1]

    retcode = stabilize(cpv)
    log.append("Retcode: ", retcode)
    if retcode == 0:
        requests.get("http://162.246.156.136/mark-stable",
                params = {'package': b64encode(cpv)})
    elif retcode != 999999:
        requests.get("http://162.246.156.136/mark-blocked",
                params = {'package': b64encode(cpv)})
    _exit(0)

