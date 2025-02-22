from contextlib import suppress
from fastapi import FastAPI
from multiprocessing import Process
from os import getenv
from redis import Redis
from requests import get
from requests.exceptions import RequestException
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from time import sleep
from traceback import format_exc

from uvicorn import run

fastapi_proc = None

try:
    redis_host = getenv("REDIS_HOST")

    if not redis_host:
        print("❌ Redis host is not set, exiting ...", flush=True)
        exit(1)

    redis_port = getenv("REDIS_PORT", "")

    if not redis_port.isdigit():
        print("❌ Redis port doesn't seem to be a number, exiting ...", flush=True)
        exit(1)

    redis_port = int(redis_port)

    redis_db = getenv("REDIS_DATABASE", "")

    if not redis_db.isdigit():
        print("❌ Redis database doesn't seem to be a number, exiting ...", flush=True)
        exit(1)

    redis_db = int(redis_db)

    redis_ssl = getenv("REDIS_SSL", "no") == "yes"

    print(
        f"ℹ️ Trying to connect to Redis with the following parameters:\nhost: {redis_host}\nport: {redis_port}\ndb: {redis_db}\nssl: {redis_ssl}",
        flush=True,
    )

    redis_client = Redis(
        host=redis_host,
        port=redis_port,
        db=redis_db,
        ssl=redis_ssl,
        socket_timeout=1,
        ssl_cert_reqs=None,
    )

    if not redis_client.ping():
        print("❌ Redis is not reachable, exiting ...", flush=True)
        exit(1)

    use_reverse_scan = getenv("USE_REVERSE_SCAN", "no") == "yes"

    if use_reverse_scan:
        print("ℹ️ Testing Reverse Scan, starting FastAPI ...", flush=True)
        app = FastAPI()
        fastapi_proc = Process(
            target=run, args=(app,), kwargs=dict(host="0.0.0.0", port=8080)
        )
        fastapi_proc.start()

        sleep(2)

        print(
            "ℹ️ FastAPI started, sending a request to http://www.example.com ...",
            flush=True,
        )

        response = get(
            "http://www.example.com",
            headers={"Host": "www.example.com"},
        )

        if response.status_code != 403:
            response.raise_for_status()

            print("❌ The request was not blocked, exiting ...", flush=True)
            exit(1)

        sleep(0.5)

        print("ℹ️ The request was blocked, checking Redis ...", flush=True)

        key_value = redis_client.get("plugin_reverse_scan_1.0.0.3:8080")

        if key_value is None:
            print(
                f'❌ The Reverse Scan key ("plugin_reverse_scan_1.0.0.3:8080") was not found, exiting ...\nkeys: {redis_client.keys()}',
                flush=True,
            )
            exit(1)
        elif key_value != b"open":
            print(
                f'❌ The Reverse Scan key ("plugin_reverse_scan_1.0.0.3:8080") was found, but the value is not "open" ({key_value.decode()}), exiting ...\nkeys: {redis_client.keys()}',
                flush=True,
            )
            exit(1)

        print(
            f"✅ The Reverse Scan key was found, the value is {key_value.decode()}",
            flush=True,
        )

        exit(0)

    use_antibot = getenv("USE_ANTIBOT", "no") != "no"

    if use_antibot:
        print("ℹ️ Testing Antibot ...", flush=True)

        firefox_options = Options()
        firefox_options.add_argument("--headless")

        print("ℹ️ Starting Firefox ...", flush=True)
        with webdriver.Firefox(options=firefox_options) as driver:
            driver.delete_all_cookies()
            driver.maximize_window()

            print("ℹ️ Navigating to http://www.example.com ...", flush=True)
            driver.get("http://www.example.com")

        sleep(0.5)

        print("ℹ️ Checking Redis ...", flush=True)

        keys = redis_client.keys("sessions_:test:*")

        if not keys:
            print(
                f"❌ No Antibot keys were found, exiting ...\nkeys: {redis_client.keys()}",
                flush=True,
            )
            exit(1)

        key_value = redis_client.get(keys[0])

        if key_value is None:
            print(
                f"❌ The Antibot key ({keys[0].decode()}) was not found, exiting ...\nkeys: {redis_client.keys()}",
                flush=True,
            )
            exit(1)

        print(
            f"✅ The Antibot key was found, the value is {key_value.decode()}",
            flush=True,
        )

        exit(0)

    print(
        "ℹ️ Sending a request to http://www.example.com/?id=/etc/passwd ...",
        flush=True,
    )

    response = get(
        "http://www.example.com/?id=/etc/passwd",
        headers={"Host": "www.example.com"},
    )

    if response.status_code != 403:
        response.raise_for_status()

        print("❌ The request was not blocked, exiting ...", flush=True)
        exit(1)

    sleep(0.5)

    print("ℹ️ The request was blocked, checking Redis ...", flush=True)

    key_value = redis_client.get("plugin_bad_behavior_1.0.0.3")

    if key_value is None:
        print(
            f'❌ The Bad Behavior key ("plugin_bad_behavior_1.0.0.3") was not found, exiting ...\nkeys: {redis_client.keys()}',
            flush=True,
        )
        exit(1)

    print(
        f"✅ The Bad Behavior key was found, the value is {key_value.decode()}",
        flush=True,
    )

    print(
        "ℹ️ Sending another request to http://www.example.com/?id=/etc/passwd ...",
        flush=True,
    )

    response = get(
        "http://www.example.com/?id=/etc/passwd",
        headers={"Host": "www.example.com"},
    )

    if response.status_code != 403:
        response.raise_for_status()

        print("❌ The request was not blocked, exiting ...", flush=True)
        exit(1)

    sleep(0.5)

    second_key_value = redis_client.get("plugin_bad_behavior_1.0.0.3")

    if second_key_value <= key_value:
        print(
            f'❌ The Bad Behavior key ("plugin_bad_behavior_1.0.0.3") was not incremented, exiting ...\nkeys: {redis_client.keys()}',
            flush=True,
        )
        exit(1)

    print(
        f"✅ The Bad Behavior key was incremented, the value is {second_key_value.decode()}",
        flush=True,
    )

    print(
        "ℹ️ Sending requests to http://www.example.com until we reach the limit ...",
        flush=True,
    )
    status_code = 0

    while status_code != 429:
        response = get(
            "http://www.example.com",
            headers={"Host": "www.example.com"},
        )

        if response.status_code not in (200, 429):
            response.raise_for_status()

        status_code = response.status_code

    sleep(0.5)

    key_value = redis_client.get("plugin_limit_www.example.com1.0.0.3/")

    if key_value is None:
        print(
            f'❌ The limit key ("plugin_limit_www.example.com1.0.0.3/") was not found, exiting ...\nkeys: {redis_client.keys()}',
            flush=True,
        )
        exit(1)

    print(
        f"✅ The limit key was found, the value is {key_value.decode()}",
        flush=True,
    )

    print(
        "ℹ️ Checking if the country key was created and has the correct value ...",
        flush=True,
    )

    key_value = redis_client.get("plugin_country_www.example.com1.0.0.3")

    if key_value is None:
        print(
            f'❌ The country key ("plugin_country_www.example.com1.0.0.3") was not found, exiting ...\nkeys: {redis_client.keys()}',
            flush=True,
        )
        exit(1)

    print(
        f"✅ The country key was found, the value is {key_value.decode()}",
        flush=True,
    )

    print(
        "ℹ️ Checking if the whitelist key was created and has the correct value ...",
        flush=True,
    )

    key_value = redis_client.get("plugin_whitelist_www.example.comip1.0.0.3")

    if key_value is None:
        print(
            f'❌ The whitelist key ("plugin_whitelist_www.example.comip1.0.0.3") was not found, exiting ...\nkeys: {redis_client.keys()}',
            flush=True,
        )
        exit(1)
    if key_value != b"ok":
        print(
            f'❌ The whitelist key ("plugin_whitelist_www.example.comip1.0.0.3") was found, but the value is not "ok" ({key_value.decode()}), exiting ...\nkeys: {redis_client.keys()}',
        )

    print(
        f"✅ The whitelist key was found, the value is {key_value.decode()}",
        flush=True,
    )

    print(
        "ℹ️ Checking if the blacklist key was created and has the correct value ...",
        flush=True,
    )

    key_value = redis_client.get("plugin_blacklist_www.example.comip1.0.0.3")

    if key_value is None:
        print(
            f'❌ The blacklist key ("plugin_blacklist_www.example.comip1.0.0.3") was not found, exiting ...\nkeys: {redis_client.keys()}',
            flush=True,
        )
        exit(1)
    if key_value != b"ok":
        print(
            f'❌ The blacklist key ("plugin_blacklist_www.example.comip1.0.0.3") was found, but the value is not "ok" ({key_value.decode()}), exiting ...\nkeys: {redis_client.keys()}',
        )

    print(
        f"✅ The blacklist key was found, the value is {key_value.decode()}",
        flush=True,
    )

    print(
        "ℹ️ Checking if the greylist key was created and has the correct value ...",
        flush=True,
    )

    key_value = redis_client.get("plugin_greylist_www.example.comip1.0.0.3")

    if key_value is None:
        print(
            f'❌ The greylist key ("plugin_greylist_www.example.comip1.0.0.3") was not found, exiting ...\nkeys: {redis_client.keys()}',
            flush=True,
        )
        exit(1)
    if key_value != b"ip":
        print(
            f'❌ The greylist key ("plugin_greylist_www.example.comip1.0.0.3") was found, but the value is not "ip" ({key_value.decode()}), exiting ...\nkeys: {redis_client.keys()}',
        )

    print(
        f"✅ The greylist key was found, the value is {key_value.decode()}",
        flush=True,
    )

    print(
        "ℹ️ Checking if the dnsbl keys were created ...",
        flush=True,
    )

    key_value = redis_client.get("plugin_dnsbl_www.example.com1.0.0.3")

    if key_value is None:
        print(
            f'❌ The dnsbl key ("plugin_dnsbl_www.example.com1.0.0.3") was not found, exiting ...\nkeys: {redis_client.keys()}',
            flush=True,
        )
        exit(1)

    print(
        f"✅ The dnsbl key was found, the value is {key_value.decode()}",
        flush=True,
    )
except SystemExit as e:
    exit(e.code)
except:
    print(f"❌ Something went wrong, exiting ...\n{format_exc()}", flush=True)
    exit(1)
finally:
    if fastapi_proc:
        fastapi_proc.terminate()
