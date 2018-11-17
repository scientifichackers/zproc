from collections import Callable


def map_plus(target: Callable, mi, ma, a, mk, k):
    """The builtin `map()`, but with superpowers."""
    if a is None:
        a = []
    if k is None:
        k = {}

    if mi is None and ma is None and mk is None:
        return []
    elif mi is None and ma is None:
        return [target(*a, **mki, **k) for mki in mk]
    elif ma is None and mk is None:
        return [target(mii, *a, **k) for mii in mi]
    elif mk is None and mi is None:
        return [target(*mai, *a, **k) for mai in ma]
    elif mi is None:
        return [target(*mai, *a, **mki, **k) for mai, mki in zip(ma, mk)]
    elif ma is None:
        return [target(mii, *a, **mki, **k) for mii, mki in zip(mi, mk)]
    elif mk is None:
        return [target(mii, *mai, *a, **k) for mii, mai in zip(mi, ma)]
    else:
        return [target(mii, *mai, *a, **mki, **k) for mii, mai, mki in zip(mi, ma, mk)]
