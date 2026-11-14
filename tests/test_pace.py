"""The frame pacer (runtime/nvn/pace.c) on a simulated clock: quick frames stay at 60, frames that don't fit hold 30."""

import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CC = shutil.which(os.environ.get('HM_CC', 'clang')) or shutil.which('cc')


@unittest.skipUnless(CC, 'no C compiler')
class Pace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = tempfile.mkdtemp(prefix='hm-pace-')
        cls.exe = os.path.join(cls.t, 'test_pace')
        subprocess.run([CC, '-std=gnu11', '-Wall', '-Werror', '-I', os.path.join(ROOT, 'runtime'),
                        os.path.join(ROOT, 'tests', 'c', 'test_pace.c'), os.path.join(ROOT, 'runtime', 'nvn', 'pace.c'),
                        '-pthread', '-o', cls.exe], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.t)

    def run_pace(self, *args):
        r = subprocess.run([self.exe, *map(str, args)], capture_output=True, text=True, check=True,
                           env={**os.environ, 'HM_LOG_PACE': '1'})
        out = dict(kv.split('=') for kv in r.stdout.split())
        return int(out['slow']), int(out['held']), r.stderr

    def test_quick_frames_stay_at_60(self):
        slow, held, _ = self.run_pace(1200, 1.1)
        self.assertEqual((slow, held), (0, 0))

    def test_cadence_wait_uncounted_held_30(self):  # (the bug: the display cadence's wait read as busy)
        slow, held, _ = self.run_pace(1200, 1.1, 'uncounted')
        self.assertGreater(held, 0)

    def test_frames_that_dont_fit_hold_30(self):
        slow, held, log = self.run_pace(600, 20)
        self.assertEqual(slow, 1)
        self.assertIn("holding the game's 30 fps mode", log)

    def test_games_own_30_mode_not_late(self):  # (interval 2: frames 33 ms apart are on time, not shown late)
        slow, held, _ = self.run_pace(1200, 1.1, 'interval2')
        self.assertEqual((slow, held), (0, 0))

    def test_games_own_wait_not_late(self):  # (33 ms frames from the game's own waits: nothing missed)
        slow, held, _ = self.run_pace(1200, 1.1, 'ownwait')
        self.assertEqual((slow, held), (0, 0))

    def test_gpu_bound_late_frames_hold_30(self):  # (33 ms frames waiting on the GPU / present: late, held)
        slow, held, log = self.run_pace(600, 1.1, 'gpubound')
        self.assertEqual(slow, 1)
        self.assertIn('0 by busy time', log)

    def test_another_presenting_thread_no_wrap(self):
        slow, held, log = self.run_pace(1200, 1.1, 'switch')
        self.assertEqual((slow, held), (0, 0))
        self.assertNotRegex(log, r'\d{10,}\.\d\d')  # (no wrapped counter, ~1.8e16 ms)


if __name__ == '__main__':
    unittest.main()
