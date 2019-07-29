#!/usr/bin/env bash

pip install -U pip-tools
pip-compile -U -v requirements.in
pip-sync