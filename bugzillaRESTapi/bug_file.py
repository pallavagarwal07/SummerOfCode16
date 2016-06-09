import requests, json, base64

# url = 'http://httpbin.org/post'
url = 'https://landfill.bugzilla.org/bugzilla-5.0-branch/rest/bug/34094/attachment?api_key=I9CjuxXrfz3HZYukXR0H353FxmznxulydmURXh1d'
# url = 'https://landfill.bugzilla.org/bugzilla-5.0-branch/rest/bug?api_key=I9CjuxXrfz3HZYukXR0H353FxmznxulydmURXh1d'

# payload = {
            # "product": 'WorldControl',
            # "component": 'EconomicControl',
            # "version": '1.0',
            # "summary": '--Please Ignore-- Testing API',
            # "description": '--Please Ignore-- Testing API',
            # "op_sys": 'Linux',
            # "platform": 'Other',
        # }

payload = {
            "encoding": "base64",
            "summary": "Test File",
            "data": base64.b64encode(open("./bug_file.py").read()),
            "file_name":"test_file",
            "content_type":"text/plain",
        }

# res = requests.get(url, json=payload)
res = requests.post(url, json=payload)
print res.text
