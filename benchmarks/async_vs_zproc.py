"""
Downloads a couple of web-pages and compares their sizes.

Prints out the time taken by ZProc and asyncio to complete the task
(excluding warm-up/setup time)

Requires the requests lib to be installed;
    $ pip install requests
"""

import asyncio

import requests
from time import time

import zproc

SAMPLES = 10

sites = list(
    {
        "https://www.yahoo.com/",
        "http://www.cnn.com",
        "http://www.python.org",
        "http://www.jython.org",
        "http://www.pypy.org",
        "http://www.perl.org",
        "http://www.cisco.com",
        "http://www.facebook.com",
        "http://www.twitter.com",
        "http://www.macrumors.com/",
        "http://arstechnica.com/",
        "http://www.reuters.com/",
        "http://abcnews.go.com/",
        "http://www.cnbc.com/",
        "https://wordpress.org/",
        "https://lists.zeromq.org/",
        "https://news.ycombinator.com/",
        "https://open.spotify.com/",
        "https://keep.google.com/",
        "https://jsonformatter.curiousconcept.com/",
        "https://www.reddit.com/",
        "https://www.youtube.com/",
        "https://bitbucket.org/",
        "http://showrss.info/timeline",
        "https://dev.solus-project.com/",
        "https://webpack.js.org/",
        "https://github.com/",
        "https://stackoverflow.com/",
        "https://github.com/",
    }
)


def print_result(results):
    winner = max(results, key=lambda x: x[0])
    print()
    print("largest:", winner[1], winner[0] / 1024, "KB")
    print()


########
# Zproc
########

ctx = zproc.Context()
ctx.state.setdefault("results", [])


@zproc.atomic
def save(state, size, url):
    print(url, int(size / 1024), "KB")

    state["results"].append((size, url))


def downloader(state, url):
    size = 0
    for _ in range(SAMPLES):
        size += len(requests.get(url, headers={"Cache-Control": "no-cache"}).text)
    size /= SAMPLES

    save(state, size, url)


s = time()

for url in sites:
    ctx.process(downloader, args=[url])
ctx.wait_all()

print_result(ctx.state["results"])

t1 = time() - s

##############
# Process Map
##############


def map_downloader(url):
    size = 0
    for _ in range(SAMPLES):
        size += len(requests.get(url, headers={"Cache-Control": "no-cache"}).text)
    size /= SAMPLES
    print(url, int(size / 1024), "KB")

    return size, url


s = time()

print_result(ctx.process_map(map_downloader, sites, count=len(sites)))

t2 = time() - s


########
# Async
########


async def main():
    loop = asyncio.get_event_loop()

    def do_req(url):
        size = 0
        for _ in range(SAMPLES):
            size += len(requests.get(url, headers={"Cache-Control": "no-cache"}).text)
        size /= SAMPLES

        print(url, int(size / 1024), "KB")

        return size, url

    futures = [loop.run_in_executor(None, do_req, site) for site in sites]

    print_result(await asyncio.gather(*futures))


loop = asyncio.get_event_loop()

s = time()

loop.run_until_complete(main())

t3 = time() - s

print("Results:\nZProc: {}sec\nProcess Map: {}sec\nAsync: {}sec".format(t1, t2, t3))
