from __future__ import print_function # Python3 cross compatibility
import portage, re, requests, json
import requests, time

try: input = raw_input                # Python3 cross compatibility
except Exception: pass

# This file tries to retrieve all bugs fitting certain parameters
# This could be:
#   all bugs for a given package,
#   all bugs in a given time period, etc.

# Save a reference to the portage tree
db = portage.db[portage.root]["porttree"].dbapi
digits = [str(k) for k in range(0,10)]

def isNum(x):
    return x in digits

def retrieve(time=30):
    # Uncomment the following if the time has to be absolute
    # If commented, the parameter passed is relative to today
    # now = datetime.datetime.now()
    # grace_period = datetime.timedelta(days = time)
    # start_time = now - grace_period
    # time = start_time.strftime('%Y%m%d')

    params = {
               #'api_key': api_key,         Optional API key (in case of login)
                'f1':'days_elapsed',      # find all bugs since last n days
                'o1':'lessthaneq',        # that is, days_elapsed < time
                'v1': time,               # where time is n
                'bug_status':'__open__',  # and the bug is still open
                'include_fields': [ 'id', 'summary', 'keywords',
                                    'severity', 'priority' ]
             }

    r = requests.get('https://bugs.gentoo.org/rest/bug', params=params)

    result = json.loads(r.text)
    bugs = []
    for k in result['bugs']:
        if 'STABLEREQ' in k['keywords']:   # We want to find bugs.
            continue                       # not stable requests,
        if 'enhancement' in k['severity']: # not enhancements,
            continue                       # and not version bumps
        if 'version' in k['summary'] and 'bump' in k['summary']:
            continue                       # and not removal requests
        if 'remov' in k['summary'] and 'request' in k['summary']:
            continue

        # Attempt to find package atom from (usually) cryptic summary
        # First see if the first word of the summary is the package
        # atom (as it should ideally be)
        summary = k["summary"]
        firstWord = re.findall(r'^[\w\-/=\.]+', summary)

        if firstWord:
            word = firstWord[0]
            if word[0] == '=' or isNum(word[-1]): word = word+'*'
            try:
                tokens = db.xmatch("match-all", word.lower())
            except Exception as e:
                pass
            if tokens:
                bugs.append((k,tokens))
                continue

        bugs.append((k,))
    # print(json.dumps(bugs, indent=4))
    return bugs
    
def getNonStablePackages(time=30):
    bugs = retrieve(time)
    unstablePackages = []
    for bug in bugs:
        if len(bug) == 1:
            continue
        unstablePackages += bug[1]
    return unstablePackages

print(getNonStablePackages())
