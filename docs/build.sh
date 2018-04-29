#!/usr/bin/env bash

sphinx-apidoc -f -o source/ ../zproc
sphinx-build . _build
