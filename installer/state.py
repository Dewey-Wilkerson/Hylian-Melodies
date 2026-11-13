"""hm-install.json in the destination: inputs, version, finished steps. Written atomically."""

import json
import os

NAME = 'hm-install.json'


class State:
    def __init__(self, dest):
        self.path = os.path.join(dest, NAME)
        self.data = {'format': 1, 'steps': {}}
        if os.path.isfile(self.path):
            with open(self.path, encoding='utf-8') as f:
                self.data = json.load(f)

    def done(self, step):
        return bool(self.data['steps'].get(step, {}).get('done'))

    def mark(self, step, **info):
        self.data['steps'][step] = {'done': True, **info}
        self.save()

    def clear(self, step):
        self.data['steps'].pop(step, None)
        self.save()

    def __getitem__(self, k):
        return self.data.get(k)

    def __setitem__(self, k, v):
        self.data[k] = v
        self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=1, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
