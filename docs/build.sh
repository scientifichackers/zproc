#!/usr/bin/env bash

rm -r _build/
sphinx-apidoc -f -o source/ ../zproc
sphinx-build . _build
