#!/usr/bin/env bash

rm -r _build/
rm -r source/
sphinx-apidoc -f -o source/ ../zproc
sphinx-build . _build
