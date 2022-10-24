#!/usr/bin/env bash
. .venv/bin/activate
python -W ignore::UserWarning -W ignore::RuntimeWarning main.py -tt USDC -p eth-usdc -r -0.15 0.15 -s simple -sd 2021-05-06 -ed 2022-08-25 -wg
