#!/usr/bin/env python
from __future__ import print_function
import portage, subprocess, base64, os, re
import solver, random, requests, sys, time
import helpers
from subprocess import PIPE, Popen

# This list will maintain a log of everything that happens
log = []

# Save a reference to the portage tree
try:
    db = portage.db[portage.root]["porttree"].dbapi
except KeyError:
    db = portage.db[portage.root]["vartree"].dbapi

# Query active USE flags for current environment
use = portage.settings["USE"].split()

# This functions returns the absolute value of the flag
# thus -X would return X and X will also return X
def abs_flag(flag):
    if flag[0] == '-':
        return flag[1:]
    return flag

# Returns an unpadded version of url safe base64 encoded string
def b64encode(s):
    return base64.urlsafe_b64encode(s).replace('=', '')

# This function uses the list "log", encodes it to base64 and
# uploads it to the server for safekeeping
def uploadLog():
    log_txt = "".join(log)
    b64log = b64encode(log_txt)
    filename = time.strftime("%Y%m%d_%H%M%S")
    payload = {
                  'filename': filename,
                  'log': b64log
              }
    response = requests.get("http://162.246.156.136/submit-log",
            params=payload)

# Custom exit function that uploads the logs before exiting
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
    args = ['emerge', '-pUuD', "="+cpv]
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

        # ret_deps is a list of CPVs of dependencies.
        # my_env is the environment for which the pretend
        # was run (same would be used to run command)
        ret_deps, my_env = dep_resolve(cpv, use_combo)

        print("Current package", cpv, "has the following dependencies:")
        print("\n".join(ret_deps))

        # In case, a dependency is unstable, it would need to be stabilized
        # first. In that case, there isn't any point with continuing this
        # stabilization
        continue_run = True

        # The list obtained also contains the package itself. Remove it
        deps = [ k for k in ret_deps if k != cpv ]
        for dep_cpv in deps:
            keywords = db.aux_get(dep_cpv, ["KEYWORDS"])[0].split()

            # Check if the current status of the package is '~amd64' (Untested)
            if '~amd64' in keywords and dep_cpv != cpv:
                payload = {
                            'parent'     : b64encode(cpv),
                            'dependency' : b64encode(dep_cpv)
                          }
                # Check what the server has to say about the package.
                # The parent has to be sent too in case the package has
                # been marked "fake - stabilized"
                response = requests.get("http://162.246.156.136/sched-dep",
                                        params=payload)

                if response.status_code != 200:
                    print("Stabilization server offline or unaccessible. Exiting")
                    _exit(0)
                else:

                    # Has already been stabilized
                    if response.text == "0":
                        print("Dependency", dep_cpv, "is already stable")
                        pass

                    # To be stabilized
                    elif response.text == "1":
                        print("Dependency", dep_cpv, "needs to be stabilized first.")
                        continue_run = False
                    
                    # Should be blocked (Tested, and fails)
                    elif response.text == "3":
                        continue_run = False

                    # In case something goes wrong on the server side
                    elif response.text == "-1":
                        print("Stabilization server returned error")
                        _exit(0)
            else:
                print("Dependency", dep_cpv, "is already stable")

        if not continue_run:
            return 999999

        args = ['emerge', '-UuD', '--autounmask-write', "--backtrack=50", "="+cpv]
        unmask = Popen(args, env=my_env, stdout=PIPE, stderr=PIPE)

        # This boolean flag takes care of running the emerge command a second
        # time if the first run causes a change in config file changes due to
        # autounmask-write
        retry = False

        for line in iter(unmask.stdout.readline, b""):
            log.append(line)
            print(line, end='')

            # If changes have been written to config files, then this condition
            # should return true. #TODO Find a better way to do this.
            if 'Autounmask changes' in line or re.search('needs? updating', line):
               retry = True
        unmask.wait()
        print("The return code was: ", unmask.returncode)

        if retry:
            # Use etc-update to commit the automask changes to file
            yes = Popen(['yes'], stdout=PIPE)
            etc = Popen(['etc-update', '--automode', '-3'], stdin=yes.stdout,
                    stdout=PIPE )

            # Save and log the output
            for line in iter(etc.stdout.readline, b""):
                log.append(line)
                print(line, end='')
            etc.wait()
            yes.terminate()

            # Finally, run the build.
            emm = Popen(['emerge', '-UuD', "--backtrack=50", "="+cpv], stdout=PIPE)
            for line in iter(emm.stdout.readline, b""):
                log.append(line)
                print(line, end='')

            # If return code != 0 (i.e. The build failed)
            if emm.wait() != 0:

                # Check to see if internet is working
                if helpers.internet_working:
                    return emm.returncode
                else:
                    print("Sorry, but you seem to have an internet failure")
                    _exit(1)
        else:
            # Similarly for first case. If emerge failed, check if
            # internet is working. If yes, then report the error
            if unmask.returncode != 0:
                if helpers.internet_working:
                    return unmask.returncode
                else:
                    print("Sorry, but you seem to have an internet failure")
                    _exit(1)
    # If everything went fine, return successful
    return 0

if __name__ == '__main__':
    # Log the input parameters
    log.append("Command: " + " ".join(sys.argv) + "\n")

    # If package is not specified, ask the server which package needs
    # to be stabilized
    if len(sys.argv) < 2:
        print("No package specified. Asking the server for one")
        package_resp = requests.get("http://162.246.156.136/request-package")

        if package_resp.status_code != 200:
            print("Stabilization server offline or unaccessible. Exiting")
            _exit(0)
        # Save whatever package name is returned from the server
        package = package_resp.text
        print("Got package:", package)
    else:
        # If package name is specified, use that
        package = sys.argv[1]

    # The package name provided may not be a valid cpv. So, use the
    # portage API to find the most appropriate match
    try:
        token = db.xmatch("match-all", package)
    except portage.exception.InvalidAtom as e:
        sys.stderr.write("Error: Invalid token name: "+str(e).strip()+"\n")
        _exit(1)
    except portage.exception.AmbiguousPackageName as e:
        sys.stderr.write("Error: Ambiguous token: "+str(e).strip()+"\n")
        _exit(1)

    log.append("Package: " + package + "\n")

    if token == []:
        sys.stderr.write("Error: No Package Found\n")
        _exit(1)

    # Remove git versions. They are not to be stabilized (ever)
    cpv = [k for k in token if '9999' not in k]

    # Choose the latest unstabilized version
    if len(cpv) > 1:
        print("Multiple versions found, assuming latest version")
    cpv = cpv[-1]

    # Try to stabilize the package and log the return code
    retcode = stabilize(cpv)
    log.append("Retcode: " + str(retcode) + "\n")

    # Return code 0 means everything went fine and the package is
    # stable
    if retcode == 0:
        requests.get("http://162.246.156.136/mark-stable",
                params = {'package': b64encode(cpv)})

    # Return code 999999 is a special code that means the package
    # stabilization was ended because of unstabilized dependencies
    # So, in cases OTHER THAN 999999, mark the package as blocked
    elif retcode != 999999:
        requests.get("http://162.246.156.136/mark-blocked",
                params = {'package': b64encode(cpv)})
    _exit(0)
