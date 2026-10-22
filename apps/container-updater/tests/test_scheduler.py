import copy
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scheduler import DEFAULT_CONFIG, ScheduleStore, next_run, validate_config
os.environ.setdefault("DCC_UPDATER_DATA", tempfile.mkdtemp(prefix="dcc-updater-tests-"))
from web import create_app


def epoch(value):
    return datetime.fromisoformat(value).timestamp()


class CalendarTests(unittest.TestCase):
    def config(self, **values):
        return validate_config({**DEFAULT_CONFIG, "enabled": True, "timezone": "Europe/Warsaw", "time": "10:30", **values}, now=epoch("2026-01-01T00:00:00+00:00"))

    def test_daily_uses_explicit_timezone_instead_of_host_clock(self):
        config = self.config()
        self.assertEqual(next_run(config, epoch("2026-10-22T08:00:00+00:00")), epoch("2026-10-22T08:30:00+00:00"))
        self.assertEqual(next_run(config, epoch("2026-10-22T08:30:00+00:00")), epoch("2026-10-23T08:30:00+00:00"))

    def test_weekly_and_monthly_short_month(self):
        weekly = self.config(kind="weekly", weekday=0)
        self.assertEqual(next_run(weekly, epoch("2026-10-22T08:00:00+00:00")), epoch("2026-10-26T09:30:00+00:00"))
        monthly = self.config(kind="monthly", month_day=31)
        self.assertEqual(next_run(monthly, epoch("2026-02-01T00:00:00+00:00")), epoch("2026-02-28T09:30:00+00:00"))

    def test_once_and_intervals_have_stable_anchors(self):
        once = self.config(kind="once", date="2026-10-23")
        self.assertEqual(next_run(once, epoch("2026-10-22T10:00:00+00:00")), epoch("2026-10-23T08:30:00+00:00"))
        self.assertIsNone(next_run(once, epoch("2026-10-23T09:00:00+00:00")))
        interval = self.config(kind="interval", date="2026-10-20", every=3, unit="days")
        self.assertEqual(next_run(interval, epoch("2026-10-22T10:00:00+00:00")), epoch("2026-10-23T08:30:00+00:00"))
        hourly = self.config(kind="interval", date="2026-10-20", every=8, unit="hours")
        self.assertEqual(next_run(hourly, epoch("2026-10-20T09:00:00+00:00")), epoch("2026-10-20T16:30:00+00:00"))

    def test_dst_missing_time_moves_forward_and_repeated_time_runs_once(self):
        config = self.config(time="02:30")
        spring = next_run(config, epoch("2027-03-27T23:00:00+00:00"))
        self.assertEqual(datetime.fromtimestamp(spring, ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M"), "2027-03-28 03:30")
        autumn = next_run(config, epoch("2026-10-24T23:00:00+00:00"))
        self.assertEqual(autumn, epoch("2026-10-25T00:30:00+00:00"))
        self.assertEqual(next_run(config, autumn), epoch("2026-10-26T01:30:00+00:00"))

    def test_invalid_inputs_are_rejected_before_execution(self):
        for values in ({"timezone": "unknown/zone"}, {"time": "25:00"}, {"kind": []},
                       {"every": 0}, {"weekday": 7}, {"panel_first": "true"},
                       {"action": "update", "targets": []}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.config(**values)

    def test_all_container_updates_require_no_individual_targets(self):
        config = self.config(action='update_all')
        self.assertEqual(config['targets'], [])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "schedule.json"
        self.store = ScheduleStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_default_off_and_claim_skips_missed_runs_without_duplicating(self):
        self.assertFalse(self.store.due("one", time.time()))
        before = epoch("2026-10-20T00:00:00+00:00")
        now = epoch("2026-10-23T12:00:00+00:00")
        self.store.save({**DEFAULT_CONFIG, "enabled": True}, before)
        claimed = self.store.claim("one", now)
        self.assertIsNotNone(claimed)
        self.assertGreater(self.store.snapshot()["next_run"], now)
        self.assertIsNone(self.store.claim("one", now))
        self.store.finish("success", "done", now)
        self.assertFalse(ScheduleStore(self.path).due("two", now))

    def test_restart_handoff_is_durable_and_owned_by_previous_instance(self):
        now = epoch("2026-10-23T12:00:00+00:00")
        self.store.save({**DEFAULT_CONFIG, "enabled": True}, now - 86400)
        self.store.claim("old", now)
        self.store.phase("awaiting_restart", "old", expected_image="sha256:" + "b" * 64, deadline=now + 600)
        loaded = ScheduleStore(self.path)
        self.assertFalse(loaded.due("old", now + 1))
        self.assertTrue(loaded.due("new", now + 1))
        self.assertEqual(loaded.snapshot()["pending"]["expected_image"], "sha256:" + "b" * 64)

    def test_corrupt_schedule_fails_closed_without_overwriting(self):
        self.path.write_text("{invalid", encoding="utf-8")
        loaded = ScheduleStore(self.path)
        self.assertTrue(loaded.snapshot()["storage_error"])
        self.assertFalse(loaded.due("one", time.time()))
        with self.assertRaises(ValueError):
            loaded.save(DEFAULT_CONFIG)
        self.assertEqual(self.path.read_text(), "{invalid")

    def test_all_container_mode_survives_restart_and_pending_handoff_without_targets(self):
        now = time.time()
        self.store.save({**DEFAULT_CONFIG, 'enabled': True, 'action': 'update_all'}, now - 86400)
        self.store.claim('old', now)
        self.store.phase('awaiting_restart', 'old', expected_image='sha256:' + 'b' * 64, deadline=now + 600)
        loaded = ScheduleStore(self.path)
        self.assertFalse(loaded.snapshot()['storage_error'])
        self.assertEqual(loaded.snapshot()['pending']['config']['action'], 'update_all')
        self.assertTrue(loaded.due('new', now + 1))

    def test_failed_claim_write_never_authorizes_a_docker_operation(self):
        now = time.time()
        self.store.save({**DEFAULT_CONFIG, "enabled": True}, now - 86400)
        with patch.object(self.store, '_write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.claim('one', now)
        self.assertIsNone(self.store.snapshot()['pending'])


class ScheduledExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.calls = []
        owner = self

        class Service:
            panel_image = "sha256:" + "a" * 64
            panel_available = False
            panel_supported = True

            def check_self_update(self, _progress):
                owner.calls.append('panel-check')
                return {"checked": True, "update_available": self.panel_available, "supported": self.panel_supported, "message": "blocked"}

            def start_self_update(self, _progress, prepare_restart=None):
                owner.calls.append('panel-install')
                prepare_restart("sha256:" + "b" * 64)
                return {"started": True}

            def _find_self_container(self):
                return SimpleNamespace(attrs={"Image": self.panel_image, "State": {"Status": "running", "Health": {"Status": "healthy"}}})

            def scan(self, _progress):
                owner.calls.append('scan')
                return [
                    {"id": "first", "name": "first", "current_image": "example/first:1", "supported": True, "auto_update_supported": True, "update_available": True},
                    {"id": "second", "name": "second", "current_image": "example/second:1", "supported": True, "auto_update_supported": True, "update_available": True},
                    {"id": "compose", "name": "compose", "current_image": "example/compose:1", "supported": True, "auto_update_supported": False, "update_available": True, "message": "Compose"},
                ]

            def update_selected(self, identifiers, _progress, *, automatic=False):
                owner.assertTrue(automatic)
                owner.calls.append(('update', identifiers))
                return [{"name": identifier, "ok": True, "result": "updated"} for identifier in identifiers]

        self.service = Service()
        self.app = create_app(self.temp.name, service_factory=lambda: self.service, print_credentials=False)

    def tearDown(self):
        self.temp.cleanup()

    def configure(self, **values):
        config = {**copy.deepcopy(DEFAULT_CONFIG), "enabled": True, **values}
        self.app.extensions['dcc_updater_schedule'].save(config, time.time() - 86400)

    def tick(self, app=None):
        app = app or self.app
        started = app.extensions['dcc_updater_scheduler_tick']()
        manager = app.extensions['dcc_updater_jobs']
        deadline = time.monotonic() + 3
        while manager.snapshot()['status'] in {'queued', 'running'} and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertNotEqual(manager.snapshot()['status'], 'error', manager.snapshot())
        return started

    def test_scan_only_does_not_update_anything_or_check_panel_unless_opted_in(self):
        self.configure()
        self.assertTrue(self.tick())
        self.assertEqual(self.calls, ['scan'])
        self.assertFalse(self.tick())

    def test_updates_only_selected_matching_repositories_and_never_auto_updates_compose(self):
        self.configure(action='update', targets=[
            {'name':'first','repository':'docker.io/example/first'},
            {'name':'second','repository':'docker.io/example/different'},
            {'name':'compose','repository':'docker.io/example/compose'},
        ])
        self.tick()
        self.assertEqual(self.calls, ['scan', ('update', ['first']), 'scan'])
        self.assertEqual(self.app.extensions['dcc_updater_schedule'].snapshot()['last_run']['status'], 'error')

    def test_panel_update_resumes_containers_only_after_verified_new_process(self):
        self.service.panel_available = True
        self.configure(panel_first=True, action='update', targets=[{'name':'first','repository':'docker.io/example/first'}])
        self.tick()
        self.assertEqual(self.calls, ['panel-check','panel-install'])
        self.assertFalse(self.tick())
        replacement = create_app(self.temp.name, service_factory=lambda: self.service, print_credentials=False)
        self.tick(replacement)  # Old image is still running: no container mutation.
        self.assertEqual(self.calls, ['panel-check','panel-install'])
        self.service.panel_image = 'sha256:' + 'b' * 64
        self.tick(replacement)
        self.assertEqual(self.calls, ['panel-check','panel-install','scan',('update',['first']),'scan'])
        self.assertIsNone(replacement.extensions['dcc_updater_schedule'].snapshot()['pending'])
        self.assertFalse(self.tick(replacement))

    def test_all_mode_uses_fresh_inventory_and_skips_blocked_unchecked_current_and_panel(self):
        rows = self.service.scan(None)
        self.calls.clear()
        rows.extend([
            {**rows[0], 'id': 'new', 'name': 'newly-installed', 'current_image': 'example/new:1'},
            {**rows[0], 'id': 'current', 'name': 'current', 'update_available': False},
            {**rows[0], 'id': 'panel', 'name': 'panel', 'is_panel': True},
            {**rows[0], 'id': 'dependent', 'name': 'dependent', 'auto_update_supported': False, 'auto_update_reason': 'Shared data with another service'},
            {**rows[0], 'id': 'ports', 'name': 'ports', 'supported': False, 'message': 'Port conflict'},
            {**rows[0], 'id': 'unchecked', 'name': 'unchecked', 'check_error': True, 'message': 'Registry timeout'},
        ])
        self.configure(action='update_all')
        with patch.object(self.service, 'scan', return_value=rows):
            self.tick()
        self.assertEqual(self.calls, [('update', ['first', 'second', 'new'])])
        outcomes = self.app.extensions['dcc_updater_jobs'].snapshot()['results']['updates']
        failures = {item['name']: item['result'] for item in outcomes if not item['ok']}
        self.assertEqual(set(failures), {'compose', 'dependent', 'ports', 'unchecked'})
        self.assertEqual(failures['unchecked'], 'Registry timeout')
        reports = self.app.extensions['dcc_updater_reports']
        deadline = time.monotonic() + 2
        while not reports.snapshot()['entries'] and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(reports.snapshot()['entries'][0]['updated'], 3)

    def test_all_mode_without_new_images_does_not_replace_or_check_panel(self):
        self.configure(action='update_all')
        with patch.object(self.service, 'scan', return_value=[{'name':'current', 'update_available':False}]):
            self.tick()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.app.extensions['dcc_updater_schedule'].snapshot()['last_run']['status'], 'success')

    def test_all_mode_keeps_panel_first_separate_and_resumes_inventory_after_restart(self):
        self.service.panel_available=True
        self.configure(action='update_all',panel_first=True)
        self.tick()
        self.assertEqual(self.calls,['panel-check','panel-install'])
        self.service.panel_image='sha256:'+'b'*64
        replacement=create_app(self.temp.name,service_factory=lambda:self.service,print_credentials=False)
        self.tick(replacement)
        self.assertEqual(self.calls,['panel-check','panel-install','scan',('update',['first','second']),'scan'])
        self.assertFalse(self.tick(replacement))

    def test_panel_blocker_stops_schedule_before_container_scan(self):
        self.service.panel_available = True
        self.service.panel_supported = False
        self.configure(panel_first=True)
        self.tick()
        self.assertEqual(self.calls, ['panel-check'])
        self.assertEqual(self.app.extensions['dcc_updater_schedule'].snapshot()['last_run']['status'], 'error')

    def test_panel_restart_timeout_does_not_start_container_scan(self):
        self.service.panel_available = True
        self.configure(panel_first=True)
        self.tick()
        replacement = create_app(self.temp.name, service_factory=lambda: self.service, print_credentials=False)
        replacement.extensions['dcc_updater_scheduler_tick'](time.time() + 601)
        deadline = time.monotonic() + 2
        while replacement.extensions['dcc_updater_jobs'].snapshot()['status'] in {'queued','running'} and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(self.calls, ['panel-check','panel-install'])
        self.assertEqual(replacement.extensions['dcc_updater_schedule'].snapshot()['last_run']['status'], 'error')

    def test_another_running_job_delays_due_schedule(self):
        self.configure()
        entered, release = threading.Event(), threading.Event()
        def work(_progress):
            entered.set(); release.wait(2)
        self.app.extensions['dcc_updater_jobs'].start('scan', work)
        self.assertTrue(entered.wait(1))
        self.assertFalse(self.app.extensions['dcc_updater_scheduler_tick']())
        self.assertEqual(self.calls, [])
        release.set()
        deadline=time.monotonic()+2
        while self.app.extensions['dcc_updater_jobs'].snapshot()['status']!='done' and time.monotonic()<deadline:
            time.sleep(.01)
        self.assertTrue(self.tick())
        self.assertEqual(self.calls, ['scan'])

    def test_interrupted_container_phase_is_not_replayed(self):
        self.configure()
        self.app.extensions['dcc_updater_schedule'].claim('old-process', time.time())
        self.app.extensions['dcc_updater_schedule'].phase('containers', 'old-process')
        replacement = create_app(self.temp.name, service_factory=lambda: self.service, print_credentials=False)
        self.tick(replacement)
        self.assertEqual(self.calls, [])
        self.assertEqual(replacement.extensions['dcc_updater_schedule'].snapshot()['last_run']['status'], 'error')


if __name__ == '__main__':
    unittest.main()
