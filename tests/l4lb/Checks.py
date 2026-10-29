"""Acceptance predicates shared with focused negative controls."""
from collections import Counter
from Fixture import payload, prefix, TAIL


def require(condition, detail):
    if not condition:
        raise AssertionError(detail)


def response(status, data, identity, model, stream=False):
    require(status == 200, f'{identity}: HTTP {status}')
    expected = prefix(identity, model) + TAIL if stream else payload(identity, model)
    require(data == expected, f'{identity}: response bytes mismatch')


def receipts(records, expected):
    actual = Counter(row['id'] for row in records)
    require(actual == Counter(expected), f'backend receipts differ: {actual} != {Counter(expected)}')
    require(all(count == 1 for count in actual.values()), 'backend replay detected')


def truncated(status, partial, identity, model, framing_failed):
    require(status == 200 and framing_failed, 'stream failure must be incomplete HTTP framing')
    require(partial == prefix(identity, model), 'unexpected partial stream bytes')
