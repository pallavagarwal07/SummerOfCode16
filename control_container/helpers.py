import httplib

def internet_working():
    conn = httplib.HTTPConnection("www.google.com")
    try:
        conn.request("HEAD", "/")
        if 'google' in dict(conn.getresponse().getheaders())['location']:
            return True
        else:
            return False
    except:
        return False
