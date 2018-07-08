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

sites = {
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
    "https://api.github.com/",
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

#######
# Zproc
#######

ctx = zproc.Context()
ctx.state.setdefault("winner", {"url": "", "size": 0})


@zproc.atomic
def tally(state, url, size):
    print(url, size / 1024, "KB")

    if size > state["winner"]["size"]:
        state["winner"] = {"url": url, "size": size}


def downloader(state, url):
    size = 0
    for i in range(SAMPLES):
        size += len(requests.get(url, headers={"Cache-Control": "no-cache"}).text)

    tally(state, url, size / SAMPLES)


s = time()

for url in sites:
    ctx.process(downloader, args=(url,))

ctx.wait_all()

winner = ctx.state["winner"]
print()
print("largest:", winner["url"], winner["size"] / 1024, "KB")
print()

t1 = time() - s

#######
# Async
#######


async def main():
    loop = asyncio.get_event_loop()

    def do_req(url):
        size = 0
        for i in range(SAMPLES):
            size += len(requests.get(url, headers={"Cache-Control": "no-cache"}).text)
        size /= SAMPLES

        print(url, size / 1024, "KB")

        return url, size

    futures = [loop.run_in_executor(None, do_req, site) for site in sites]

    winner = {"url": "", "size": 0}
    for url, size in await asyncio.gather(*futures):
        if size > winner["size"]:
            winner = {"url": url, "size": size}

    print()
    print("largest:", winner["url"], winner["size"] / 1024, "KB")
    print()


loop = asyncio.get_event_loop()

s = time()

loop.run_until_complete(main())

t2 = time() - s

print("Async: {}sec, ZProc: {}sec".format(t1, t2))
