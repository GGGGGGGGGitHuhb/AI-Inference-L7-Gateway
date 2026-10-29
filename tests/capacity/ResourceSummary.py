"""Sampled resource evidence, with real windows and 1-tick quantization retained."""
import os
from Common import rows


def summarize(root, start, duration):
    samples = list(rows(root, 'resources'))
    processes = {}
    peak_rss = peak_fds = 0
    intervals = []
    for index, row in enumerate(samples):
        peak_rss = max(peak_rss, sum(p['rss'] for p in row['processes'].values()))
        peak_fds = max(peak_fds, sum(p['fds'] for p in row['processes'].values()))
        if index:
            intervals.append((row['start'] - samples[index-1]['start']) / 1e6)
        if not start <= row['start'] <= start + duration * 1e9:
            continue
        for name, value in row['processes'].items():
            item = processes.setdefault(name, {'first_ns': row['start'], 'first': value})
            item.update(last_ns=row['start'], last=value)
    hz = os.sysconf('SC_CLK_TCK')
    for value in processes.values():
        seconds = (value['last_ns'] - value['first_ns']) / 1e9
        value['window_seconds'] = seconds
        value['ticks_per_second'] = hz
        value['core'] = (value['last']['ticks'] - value['first']['ticks']) / hz / seconds if seconds else None
        value['one_tick_core'] = 1 / hz / seconds if seconds else None
        value['thread_cores'] = {tid: (ticks - value['first']['threads'][tid]) / hz / seconds
                                 for tid, ticks in value['last']['threads'].items()
                                 if tid in value['first']['threads'] and seconds}
    return {'sampled_peak_rss': peak_rss, 'sampled_peak_fds': peak_fds,
            'interval_ms_min': min(intervals) if intervals else None,
            'interval_ms_max': max(intervals) if intervals else None,
            'sampling_read_ns_total': sum(row['end'] - row['start'] for row in samples),
            'processes': processes}
