#!/usr/bin/env python

import json
import os
import traceback

from time import sleep

import rx
from rx import operators as ops
import concurrent.futures


def get_file_names(dir_path, sub_origin):

    file_names = []
    for (dirpath, dirnames, filenames) in os.walk(f'{dir_path}/{sub_origin}'):
        # file_names = [grid.replace('.json', '') for grid in filenames if '.json' in grid]

        file_names.extend(filenames)
        break

    # print(file_names)

    return file_names


def beautify_file(file_name, dir_path, origin_dir='COMPACT', destination_dir='BEAUTY'):
    origin_full_path = f'{dir_path}/{origin_dir}/{file_name}.json'

    destination_dir = f'{dir_path}/{destination_dir}'

    print(f"destination_dir: {destination_dir}")

    if not os.path.exists(destination_dir):
        os.mkdir(destination_dir)

    destination_full_path = f'{destination_dir}/{file_name}_pretty.json'

    with open(origin_full_path) as json_file:
        data = json.load(json_file)

        j = json.dumps(data, indent=2, sort_keys=True)

        print(type(j))

        with open(destination_full_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    return f"pretty: {destination_full_path}"


def beautify_all_in_path(dir_path, sub_origin='COMPACT', sub_destination='BEAUTY'):

    uglies = get_file_names(dir_path, sub_origin)

    source = rx.from_(uglies)
    max_threads = 5

    with concurrent.futures.ProcessPoolExecutor(max_threads) as executor:
        composed = source.pipe(
            ops.filter(lambda file_name: '.json' in file_name),
            ops.map(lambda file_name: file_name.replace('.json', '')),
            ops.flat_map(
                lambda file_name: executor.submit(
                    beautify_file,
                    file_name,
                    dir_path,
                    sub_origin,
                    sub_destination,
                )
            )
        )
        composed.subscribe(lambda file_name: print(f"Received {file_name}"))
