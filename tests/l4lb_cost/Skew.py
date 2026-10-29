"""Adversarial long-stream placement using the already accepted S1 fixture."""
import json
from pathlib import Path
from Common import require, write
from RunTopology import Matrix


class SkewMatrix(Matrix):
    def spawn_gateway(self, index):
        path = self.output / f'gateway-{index}.json'
        config = json.loads(path.read_text())
        config['admission']['max_inflight'] = 8
        config['admission']['max_inflight_per_backend'] = 8
        config['upstream_pool']['max_connections'] = 8
        path.write_text(json.dumps(config, indent=2) + '\n')
        super().spawn_gateway(index)


def run(args):
    matrix = SkewMatrix(args)
    error = None
    distribution = [0, 0]
    occupancy = [0, 0]
    try:
        matrix.setup()
        matrix.startup()
        held = []
        long_gateway = None
        for index in range(4):
            conn, target = matrix.connect()
            distribution[target] += 1
            if long_gateway is None:
                long_gateway = target
            require(target == long_gateway, 'constructed RR long-flow placement differs')
            identity = f'skew-long-{index}'
            state = matrix.stream(conn, target, identity)
            held.append((conn, state, identity))
            occupancy[target] += 1
            short_target = matrix.exchange(f'skew-short-{index}')
            distribution[short_target] += 1
        require(distribution == [4, 4] and sorted(occupancy) == [0, 4], 'skew snapshot differs')
        require(all(not state[2].is_set() for _, state, _ in held), 'long stream released before snapshot')
        matrix.event('skew_snapshot', accepted=distribution, in_flight=occupancy)
        for conn, state, identity in held:
            matrix.finish_stream(state, identity)
            conn.close()
        matrix.audit()
    except Exception as failure:
        error = repr(failure)
    finally:
        cleanup = matrix.close()
        if cleanup:
            error = str(error) + repr(cleanup)
        write(matrix.output / 'result.json', {'status': 'FAIL' if error else 'PASS', 'error': error,
                                            'connections': distribution, 'in_flight_snapshot': occupancy})
    require(error is None, 'skew failed: ' + str(error))
    return {'connections': distribution, 'in_flight_snapshot': occupancy, 'request_count': 8}
