#!/usr/bin/python

import collections
import itertools
import json
import optparse
import paho.mqtt.client as mqtt
import sys
import threading
import time
from RPi import GPIO

parser = optparse.OptionParser()
parser.add_option('--host', action='store', dest='host', default='127.0.0.1')
parser.add_option('--port', action='store', dest='port', type='int', default=1883)
parser.add_option('--user', action='store', dest='user', default='rtl_433')
parser.add_option('--pass', action='store', dest='password', default='334_ltr')

OFF = 0
ON = 1
BLINK = 2
BLINK_DURATION = 30
BLINK_FREQ = 0.2

Door = collections.namedtuple('Door', 'id name pin')
DOORS = [
    Door(2651912, 'Garage Door', 18),
    Door(2898343, 'Front Door', 17),
    Door(2959527, 'Back Door', 27),
    Door(None, 'Unknown', 22),
]


def ts():
    return time.time()


class Led(object):

    def __init__(self, pin, state=0, val=GPIO.LOW, t=None):
        t = t or ts()
        self.pin = pin
        self._state = state
        self._state_changed = t
        self._val = val
        self._val_changed = t
        self._mu = threading.Lock()

    @property
    def state(self):
        return self._state

    def set_state(self, state, t):
        with self._mu:
            if self._state == state:
                return
            self._state = state
            self._state_changed = t

    def tick(self, t):
        if self._state == OFF:
            if self._val != GPIO.LOW:
                self._set_val(GPIO.LOW, t)
            return
        if self._state == ON:
            if self._val != GPIO.HIGH:
                self._set_val(GPIO.HIGH, t)
            return
        if self._state == BLINK:
            if t - self._state_changed >= BLINK_DURATION:
                self.set_state(OFF, t)
                return
            if t - self._val_changed >= BLINK_FREQ:
                self._set_val(ON if self._val == OFF else OFF, t)

    def _set_val(self, val, t):
        with self._mu:
            self._val = val
            self._val_changed = t
            GPIO.output(self.pin, self._val)


class LightShow(object):

    def __init__(self, doors, c):
        t = ts()
        self.doors = {d.id: d for d in doors}
        self.leds = {d.pin: Led(d.pin, state=BLINK, t=t) for d in doors}
        c.on_message = self.on_message

    def run(self):
        while True:
            for led in self.leds.values():
                led.tick(ts())
            time.sleep(0.1)

    def on_message(self, c, ud, msg):
        if not msg.topic.endswith('/closed'):
            return
        door_id = int(msg.topic.split('/')[-2])
        door = self.doors.get(door_id, self.doors[None])
        door_open = str(msg.payload) == '0'
        door_open_str = 'open' if door_open else 'closed'
        state = ON if door_open else BLINK
        print('Door: %s (id=%s) is %s (state=%s)' %
              (door.name, door_id, door_open_str, state))
        self.leds[door.pin].set_state(state, ts())


def main():
    opts, args = parser.parse_args()

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup([d.pin for d in DOORS], GPIO.OUT, initial=GPIO.LOW)

    c = mqtt.Client()
    c.username_pw_set(opts.user, opts.password)
    c.connect(opts.host, opts.port, 60)
    c.subscribe('rtl_433/#')
    ls = LightShow(DOORS, c)
    try:
        c.loop_start()
        ls.run()
    except KeyboardInterrupt:
        print('Shutting down...')
    finally:
        c.loop_stop()
        GPIO.cleanup()


if __name__ == '__main__':
    main()
