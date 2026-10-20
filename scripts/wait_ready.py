import time
import urllib.request

for _attempt in range(50):
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/readyz", timeout=1)
        break
    except OSError:
        time.sleep(0.2)
else:
    raise SystemExit("ATLAS readiness check failed")
