"""
Downloads a couple of web-pages and compares their sizes.

Prints out the time taken by different frameworks to complete the task
(excluding warm-up/setup time)
"""

import asyncio
from time import time

import requests

import zproc

SAMPLES = 1

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

t = time() - s

print("Pure ZProc took: {} sec".format(t))

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

t = time() - s

print("ZProc Process Map took: {} sec".format(t))


########
# Async
########

import grequests


async def main():
    results = []
    for site in sites:
        size = 0
        for _ in range(SAMPLES):
            req = await grequests.get(site, headers={"Cache-Control": "no-cache"})
            size += len(req.text)
        size /= SAMPLES

        results.append((size, site))

    print_result(results)


loop = asyncio.get_event_loop()

s = time()

loop.run_until_complete(main())

t = time() - s

print("Asyncio took: {} sec".format(t))

#######
# Trio
#######
#
#
# async def downloader():
#     size = 0
#     for _ in range(SAMPLES):
#         size += len(requests.get(url, headers={"Cache-Control": "no-cache"}).text)
#     size /= SAMPLES
