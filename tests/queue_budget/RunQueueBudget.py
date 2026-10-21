"""One bounded S2 run. All transport, scheduling and storage reuse S1."""
import argparse
import json
import os
from pathlib import Path
import platform
import signal
import time

from QueuePlan import build_plan, configuration
from Budget import RunBudget, save, append, write
from Infrastructure import ROOT, Host, Sampler, sha
from RunExperiments import Cell, interrupt, sha_bytes
from Plan import request
from Client import HASHES
from QueueAudit import analyze


class QueueCell(Cell):
    def start_gateway(self):
        ports = [b['port'] for b in self.backends]
        self.targets = ports
        if self.cell['path'] != 'D':
            self.host = Host(self.args.host, configuration(self.cell, ports), self.output)
            self.targets = [self.host.port]


def close_unstarted(root, plan):
    missing = [dict(id=a['id'], outcome='not_started') for c in plan['cells']
               for a in c['attempts'] if not (root/c['id']/(a['id']+'.json')).exists()]
    if missing:
        write(root/'unstarted.json', json.dumps(missing).encode(), emergency=True)
    return missing


def run(args):
    root = Path(args.output).resolve()
    root.mkdir(exist_ok=False, parents=True)
    plan = build_plan(); completed = []; sampler = None; started = time.monotonic()
    with RunBudget(root) as budget:
        try:
            save(root/'plan.json', plan)
            sources = list((ROOT/'tests/queue_budget').rglob('*.py')) + list((ROOT/'tests/queue_budget/configs').glob('*.json'))
            sources += list((ROOT/'tests/experiments').glob('*.py')) + list((ROOT/'src').rglob('*.cpp')) + list((ROOT/'src').rglob('*.h'))
            save(root/'manifest.json', dict(arguments=vars(args), platform=platform.platform(),
                affinity=sorted(os.sched_getaffinity(0)), cpu_count=os.cpu_count(),
                payload_hashes=HASHES, source_hashes={str(p.relative_to(ROOT)): sha(p) for p in sources},
                host_sha256=sha(args.host), plan_sha256=sha(root/'plan.json'),
                requests={a['id']: sha_bytes(request(c, a)) for c in plan['cells'] for a in c['attempts']},
                configuration_templates={c['id']: configuration(c, [1, 2] if c['group'] == 'Q' else [1]) for c in plan['cells']}))
            signal.signal(signal.SIGALRM, interrupt)
            signal.signal(signal.SIGTERM, interrupt)
            signal.alarm(900)
            sampler = Sampler(budget, root)
            for cell in plan['cells']:
                remaining = 900 - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('whole-run 900s deadline')
                signal.setitimer(signal.ITIMER_REAL, min(60, remaining))
                print('START', cell['id'], flush=True)
                result = QueueCell(cell, args, root, None, budget).run()
                signal.setitimer(signal.ITIMER_REAL, max(.001, 900 - (time.monotonic() - started)))
                completed.append(dict(cell=cell, **result))
                append(root/'completed-cells.jsonl', completed[-1])
                print('DONE', cell['id'], result['counts'], flush=True)
            sampler.stop(); sampler = None
            budget.finish()
            analysis = analyze(root)
            save(root/'result.json', dict(status=analysis['status'], seconds=time.monotonic()-started,
                 cells=len(completed), charged=budget.used, limits=budget.limits,
                 direct_paths=len(budget.direct_paths), children=len(budget.children)))
            return 0 if analysis['status'] == 'PASS' else 2
        except BaseException as error:
            save(root/'result.json', dict(status='FAIL', error=repr(error), cells=len(completed),
                 seconds=time.monotonic()-started, charged=budget.used))
            raise
        finally:
            signal.alarm(0)
            try:
                if sampler:
                    sampler.stop()
            finally:
                close_unstarted(root, plan)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=True)
    parser.add_argument('--output', required=True)
    return run(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
