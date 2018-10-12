#!/usr/bin/env bash

rm -r _build/

function build {
    sphinx-build . _build
}

if [ "$1" == "loop" ]; then
    while true; do
        build
        test $? -ne 0 && break
        sleep 1
    done
else
    build
fi