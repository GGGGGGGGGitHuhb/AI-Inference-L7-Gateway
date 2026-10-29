"""Task-local E0 provenance and idle sampling, actual tracked-source hashes."""
import argparse
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import time
from Common import Chunks, MIB, digest, now, proc, write


def identity(root):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args]).decode()
    paths = git('ls-files', '-z', 'src', 'third_party', 'CMakeLists.txt', 'cmake').split('\0')
    return {'root': str(root), 'head': git('rev-parse', 'HEAD').strip(),
            'source_diff': git('diff', 'HEAD', '--', 'src', 'third_party', 'CMakeLists.txt', 'cmake'),
            'files': {p: digest((Path(root) / p).read_bytes()) for p in paths if p and (Path(root) / p).is_file()}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--gateway', required=True)
    parser.add_argument('--l4lb', required=True)
    parser.add_argument('--tag', default='before')
    args = parser.parse_args()
    root = Path(args.output)
    root.mkdir(exist_ok=True, parents=True)
    write(root / ('source-' + args.tag + '.json'), {'gateway': identity(Path(__file__).resolve().parents[2]),
          'l4lb': identity('/home/power/projects/L4-LoadBalancer-withXDP'),
          'binaries': {p: digest(Path(p).read_bytes()) for p in [args.gateway, args.l4lb]}})
    if args.tag != 'before':
        return
    read = lambda p: Path(p).read_text() if Path(p).exists() else None
    write(root / 'environment.json', {'platform': platform.platform(), 'cpu_count': os.cpu_count(),
          'clock': vars(time.get_clock_info('monotonic')), 'ticks_per_second': os.sysconf('SC_CLK_TCK'),
          'fd_limit': resource.getrlimit(resource.RLIMIT_NOFILE), 'affinity': sorted(os.sched_getaffinity(0)),
          'meminfo': read('/proc/meminfo'), 'cpuinfo': read('/proc/cpuinfo'),
          'cgroup_cpu_max': read('/sys/fs/cgroup/cpu.max'), 'cgroup_memory_max': read('/sys/fs/cgroup/memory.max'),
          'tools': {name: shutil.which(name) for name in ['strace', 'perf', 'taskset', 'cmake', 'ninja']},
          'build': {'type': 'Release', 'L4LB_BUILD_XDP': 'OFF', 'L4LB_BUILD_XDP_LOADER': 'OFF'},
          'route': {k: os.getenv(k) for k in ['TMPDIR', 'TMP', 'TEMP', 'XDG_CACHE_HOME', 'PYTHONPYCACHEPREFIX']}})
    output = Chunks(root, 'idle', MIB)
    for _ in range(30):
        start = now()
        output.row({'start': start, 'controller': proc(os.getpid()), 'system_stat': read('/proc/stat'),
                    'loadavg': read('/proc/loadavg'), 'end': now()})
        time.sleep(.1)
    output.close()


if __name__ == '__main__':
    main()
