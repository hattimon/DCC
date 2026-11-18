"""Measure one synchronized refresh burst against an isolated DCC Web app."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'apps/dcc-web'), str(ROOT)]

from cryptography.fernet import Fernet
from web import create_app


def run(clients, containers, samples, backend_ms):
    stats = [{'Name': f'fixture-{i}', 'ID': f'{i:064x}', 'CPUPerc': '0.47%',
              'MemUsage': '51.3MiB / 4GiB', 'MemPerc': '1.25%', 'NetIO': '7kB / 8kB',
              'BlockIO': '14MB / 2.5MB', 'PIDs': '15'} for i in range(containers)]
    calls = 0
    lock = threading.Lock()

    class Backend:
        def __init__(self, profile):
            pass

        def stats(self):
            nonlocal calls
            with lock:
                calls += 1
            time.sleep(backend_ms / 1000)
            return stats

    with tempfile.TemporaryDirectory(prefix='dcc-benchmark-') as data:
        app = create_app({'TESTING': True, 'DATA_DIR': data, 'MASTER_KEY': Fernet.generate_key()},
                         backend_factory=Backend)
        state = app.extensions['dcc_state']
        browser = app.test_client()
        browser.get('/login')
        with browser.session_transaction() as session:
            csrf = session['csrf']
        assert browser.post('/setup', data={'username': 'fixture', 'password': 'benchmark-fixture-only', 'csrf': csrf}).status_code == 302
        cookie = browser.get_cookie(app.config['SESSION_COOKIE_NAME'])
        for _ in range(samples):
            state.sample('local', stats)
        barrier = threading.Barrier(clients)

        def refresh(_):
            client = app.test_client()
            client.set_cookie(cookie.key, cookie.value)
            barrier.wait(timeout=10)
            response = client.get('/api/monitoring?history=0')
            if response.status_code != 200:
                raise RuntimeError(f'Monitoring fixture returned HTTP {response.status_code}')
            return len(response.data)

        tracemalloc.start()
        wall, cpu = time.perf_counter(), time.process_time()
        with ThreadPoolExecutor(max_workers=clients) as pool:
            response_sizes = list(pool.map(refresh, range(clients)))
        result = dict(clients=clients, containers=containers, prior_samples=samples, simulated_backend_ms=backend_ms,
                      docker_stats_calls=calls, sqlite_samples_written=state.rows('SELECT COUNT(*) AS n FROM samples')[0]['n'] - samples,
                      response_bytes_total=sum(response_sizes), wall_ms=round((time.perf_counter() - wall) * 1000, 1),
                      process_cpu_ms=round((time.process_time() - cpu) * 1000, 1),
                      peak_python_bytes=tracemalloc.get_traced_memory()[1])
        tracemalloc.stop()
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clients', type=int, default=8, choices=range(1, 17))
    parser.add_argument('--check', action='store_true', help='Check Docker calls, sample writes and response size')
    args = parser.parse_args()
    result = run(args.clients, containers=48, samples=120, backend_ms=120)
    print(json.dumps(result, indent=2))
    # Allow one late client on a busy CI runner. Timings are observations only.
    calls, writes = result['docker_stats_calls'], result['sqlite_samples_written']
    if args.check and (
        calls != writes or calls not in (1, 2)
        or result['response_bytes_total'] > 16 * 1024 * args.clients
    ):
        raise SystemExit('Container monitoring exceeded its call, write or response budget.')
