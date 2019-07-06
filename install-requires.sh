#!/usr/bin/env bash

pip install pip-tools
pip-compile -v requirements.in
pip-sync