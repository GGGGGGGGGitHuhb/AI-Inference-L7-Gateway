"""Record actual inputs, including dirty tracked files, without editing either repo."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(root):
    root = Path(root).resolve()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args]).decode()
    paths = git('ls-files', '-z', 'src', 'third_party', 'CMakeLists.txt', 'cmake').split('\0')
    return {'root': str(root), 'head': git('rev-parse', 'HEAD').strip(),
            'diff': git('diff', 'HEAD', '--', 'src', 'CMakeLists.txt', 'cmake'),
            'files': {p: sha(root / p) for p in paths if p and (root / p).is_file()}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    with open(args.output, 'x') as file:
        json.dump(snapshot(args.source), file, indent=2)
        file.write('\n')
