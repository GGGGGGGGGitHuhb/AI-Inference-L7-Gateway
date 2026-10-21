"""V0.4/S2 frozen plan; S1 mechanisms remain imported and immutable."""
from pathlib import Path
import sys

EXPERIMENTS = Path(__file__).resolve().parents[1] / 'experiments'
sys.path.insert(0, str(EXPERIMENTS))
from Plan import configuration as original_configuration

VARIANTS = {'Z': (0, 500), 'B': (8, 500), 'C': (8, 100)}
CONFIG_FILES = {'Z': 'no-queue.json', 'B': 'baseline-500ms.json',
                'C': 'candidate-100ms.json'}


def build_plan():
    cells = []

    def add(group, repeat, variant='', rate=0, processes=1):
        count, timeout = VARIANTS[variant] if variant else (0, 500)
        cell = dict(id=f'{len(cells):02}-{group}-{repeat}-{rate}-{variant or "D"}',
                    group=group, repeat=repeat, path='P' if group == 'Q' else 'D',
                    variant=variant, rate=rate, processes=processes,
                    concurrency=0 if rate else 8, queue_count=count,
                    queue_timeout_ms=timeout, nodelay=False,
                    formal=120 if group == 'Q' else 200, warmup=10)
        cell['attempts'] = [dict(id=f'{cell["id"]}-{phase}-{i:03}', phase=phase,
                                index=i, slow=False, long=group == 'Q' and i % 4 == 3)
                            for phase in ('warmup', 'formal')
                            for i in range(cell[phase])]
        cells.append(cell)

    add('T', 0)
    add('T', 1, processes=2)
    for repeat, order in enumerate(('ZBC', 'CBZ', 'BZC')):
        for rate in (5, 60):
            for variant in order:
                add('Q', repeat, variant, rate)
    add('T', 2)
    return dict(cells=cells, formal=2760, warmup=210, total=2970,
                slo={'Q': {'ttft': .25, 'e2e': .5}, 'T': {'e2e': .1}})


def configuration(cell, ports):
    value = original_configuration(cell, ports)
    value['listen_address'] = '127.0.0.1'
    if cell['group'] == 'Q':
        value['admission']['queue_timeout_ms'] = cell['queue_timeout_ms']
    return value


def normalize_config(value):
    import copy
    value = copy.deepcopy(value)
    value['listen_port'] = 0
    for index, backend in enumerate(value['models'][0]['backends']):
        backend['port'] = index + 1
    return value
