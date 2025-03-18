# This software is licensed under the MIT License, which allows you to use,
# copy, modify, merge, publish, distribute, and sell copies of the software,
# with the requirement to include the original copyright notice and this
# permission notice in all copies or substantial portions of the software.
#
# The software is provided 'as is', without any warranty.

import os

# Helper functions and callbacks
def read_file(file_name):
    with open(file_name, 'r') as file:
        data = file.read().replace('\n', '')

    return data

def read_version():
    if os.path.isfile('./VERSION'):
        return read_file('./VERSION')

    return read_file('../VERSION')

def to_gb(total):
    return str(round(float(total[0]) / 1024 / 1024 / 1024, 2))
