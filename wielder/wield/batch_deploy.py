#!/usr/bin/env python
import logging

# import concurrent.futures
# from concurrent.futures import as_completed

from threading import current_thread

import rx
from rx import operators as ops

from rx.scheduler import CurrentThreadScheduler
from wielder.wield.enumerator import WieldAction


def output(result):
    print(f"Type of result: {type(result)}")
    # [print(f"result: {r}") for r in result]
    print(result)


def on_done(result):
    print(f"Type of result: {type(result)}")
    # [print(f"result: {r}") for r in result]
    print(result)


def deploy_batch(action, batch, func_map):
    init_tuples = []

    for deploy in batch:
        deploy_func = func_map[deploy]

        init_tuples.append((deploy_func, action, False, True))

    print(f'{init_tuples}')

    source = rx.from_(init_tuples)

    thread_pool_scheduler = rx.scheduler.NewThreadScheduler()

    new_dict = source.pipe(
        ops.flat_map(lambda s: rx.of(s).pipe(
            ops.map(lambda a: a[0](a[1], a[2], a[3])),
            ops.subscribe_on(thread_pool_scheduler)
        )),
        ops.to_dict(lambda x: x)
    ).run()

    print(f"From main: {format(current_thread())}")
    print(str(new_dict))

    # with concurrent.futures.ProcessPoolExecutor(len(init_tuples)) as executor:
    #
    #     composed = source.pipe(
    #         ops.flat_map(lambda s: executor.submit(
    #             s[0],
    #             action=s[1],
    #             observe=s[2],
    #             auto_approve=s[3]
    #         ))
    #     )
    #     composed.subscribe(output)
    #
    # for future in as_completed(composed):
    #     future.add_done_callback(on_done)
    #     print(f'future job n°{future.result()} ended')


def wield_deployment_batches(conf, action, key_path, func_map):
    """
    bootstrap_jobs: {

      parallel: true

      ordered_deployments: [
        [bootcassandra, bootkafka]
      ]
    }
    :param func_map:
    :param conf: project Hocon which includes the key e.g. bootstrap_jobs
    :param action: WieldAction
    :param key_path: a list of keys to the deployment batches config tree.
    :return:
    """

    deploy_batches = conf[key_path[0]]

    for key in key_path[1:]:
        deploy_batches = deploy_batches[key]

    parallel = deploy_batches.parallel

    batches = deploy_batches.ordered_deployments

    if action == WieldAction.DELETE:
        batches = batches[::-1]

        new_batches = []

        for batch in batches:
            new_batches.append(batch[::-1])

        batches = new_batches

    for batch in batches:

        if parallel:
            deploy_batch(action, batch, func_map)

        observe = False if action == WieldAction.DELETE else True

        if observe:

            for dep in batch:
                logging.info(f"Starting observation of batch {batch}.")

                deploy_func = func_map[dep]
                print(f'{dep}: {deploy_func}')

                deploy_func(
                    action=action,
                    observe=observe,
                    auto_approve=True
                )

            print(f'\nbatch complete\n')

