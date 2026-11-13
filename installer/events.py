"""JSON events on stdout (one per line) plus a full text log."""

import json
import sys
import time

from . import messages


class Events:
    def __init__(self, log_path=None, stream=None):
        self.stream = stream or sys.stdout
        self.log = open(log_path, 'a', encoding='utf-8') if log_path else None
        self.last_pct = {}

    def _emit(self, ev):
        self.stream.write(json.dumps(ev, separators=(',', ':')) + '\n')
        self.stream.flush()
        self.write_log(f'[{ev["event"]}] ' + json.dumps({k: v for k, v in ev.items() if k != 'event'}))

    def write_log(self, line):
        if self.log:
            self.log.write(time.strftime('%H:%M:%S ') + line.rstrip('\n') + '\n')
            self.log.flush()

    def start(self, steps):
        self._emit({'event': 'start', 'steps': steps})

    def step(self, step):
        self.last_pct[step] = -1
        self._emit({'event': 'step', 'step': step, 'msg': messages.STEPS.get(step, step)})

    def progress(self, step, pct):
        pct = max(0, min(100, int(pct)))
        if pct != self.last_pct.get(step):
            self.last_pct[step] = pct
            self._emit({'event': 'progress', 'step': step, 'pct': pct})

    def info(self, msg, **args):
        self._emit({'event': 'info', 'msg': msg, 'args': args, 'text': messages.text(msg, args)})

    def warning(self, msg, **args):
        self._emit({'event': 'warning', 'msg': msg, 'args': args, 'text': messages.text(msg, args)})

    def error(self, msg, **args):
        self._emit({'event': 'error', 'msg': msg, 'args': args, 'text': messages.text(msg, args)})

    def end(self, result, **args):
        self._emit({'event': 'end', 'result': result, **args})


class SetupError(Exception):
    def __init__(self, msg, **args):
        super().__init__(messages.text(msg, args))
        self.msg, self.args_ = msg, args
