#!/usr/bin/env bash

pip install -U pip-tools
pip-compile -v requirements.in
pip-sync