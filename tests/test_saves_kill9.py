"""M7 acceptance: a save made in play survives `kill -9` and loads again.

Needs a built game and an extracted install; opens a window for about two minutes:
  HM_TEST_EXE=~/.cache/hylian-melodies/build/hylian-melodies HM_TEST_GAME_DIR=~/.cache/hylian-melodies/dev \
      python3 -m unittest tests.test_saves_kill9
The install's profile/ is moved aside for the test and put back afterwards.
"""

import os
import re
import shutil
import signal
import subprocess
import time
import unittest

EXE, GAME = os.environ.get('HM_TEST_EXE'), os.environ.get('HM_TEST_GAME_DIR')


@unittest.skipUnless(EXE and GAME, 'needs HM_TEST_EXE and HM_TEST_GAME_DIR')
class SaveSurvivesKill(unittest.TestCase):
    def setUp(self):
        self.profile = os.path.join(GAME, 'profile')
        self.kept = self.profile + '.test-kept'
        if os.path.exists(self.profile):
            os.rename(self.profile, self.kept)
        self.log = os.path.join(os.path.dirname(EXE), 'logs', 'hylian-melodies.log')

    def tearDown(self):
        shutil.rmtree(self.profile, ignore_errors=True)
        if os.path.exists(self.kept):
            os.rename(self.kept, self.profile)

    def run_game(self, script, seconds, kill):
        env = dict(os.environ, HM_GAME_DIR=GAME, HM_INPUT_SCRIPT=script)
        if not kill:
            env['HM_RUN_SECONDS'] = str(seconds)
        p = subprocess.Popen([EXE], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            p.wait(timeout=seconds + (0 if kill else 30))
        except subprocess.TimeoutExpired:
            p.send_signal(signal.SIGKILL)
            p.wait()
        with open(self.log, errors='replace') as f:
            return f.read()

    def test_new_game_save_survives_kill_and_loads(self):
        save = os.path.join(self.profile, 'save_0', 'savedata.xml')
        # new game: slot, start game, skip the calibration, on into play; killed without warning at 55 s
        log = self.run_game('700:a,900:a,1100:a,1300:b,1500:a,1700:a,1900:a', 55, kill=True)
        commits = re.findall(r'\[save\] committed profile/save_0/savedata.xml', log)
        self.assertTrue(commits, 'the game never committed a save')
        size = os.path.getsize(save)
        self.assertGreater(size, 1000)
        time.sleep(1)
        # restart: the game reads the whole committed save back
        log = self.run_game('', 25, kill=False)
        self.assertIn(f'[save] read profile/save_0/savedata.xml off 0 size {size}', log)
        self.assertNotIn('signal 11', log)


if __name__ == '__main__':
    unittest.main()
