#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
from subprocess import Popen, PIPE


_xrandr = Popen(['xrandr'], stdout=PIPE, stderr=PIPE, universal_newlines=True)
xrandr, err = _xrandr.communicate()


def get_screens_info():
    global xrandr
    out = {}
    for line in xrandr.split('\n'):
        temp_out = {'state': '', 'primary': '', 'res': '',
                    'offset': ''}
        if 'unknown' in line or 'disconnected' in line:
            continue
        if 'connected' in line:
            try:
                '''
                Try to get following line:

                DP2-2 connected primary 1920x1080+1600+0 (normal left
                inverted right x axis y axis) 600mm x 340mm

                or this

                eDP connected (normal left inverted right x axis y axis)
                '''
                re_screen = re.search(r'^([a-zA-Z0-9\-]+)\s+(connected|disconnected)\sprimary\s(\d+x\d+)\+(\d+\+\d+) \(.*', line)
                if re_screen is None:
                    continue
                else:
                    temp_out['state'] = re_screen.group(2)
                    temp_out['primary'] = True
                    temp_out['res'] = re_screen.group(3)
                    temp_out['offset'] = re_screen.group(4)
            except(AttributeError):
                if re_screen is None:
                    continue
                else:
                    re_screen = re.search(r'^([a-zA-Z0-9\-]+)\s+(connected|disconnected)\s(\d+x\d+)\+(\d+\+\d+) \(.*', line)
                    temp_out['state'] = re_screen.group(2)
                    temp_out['primary'] = False
                    temp_out['res'] = re_screen.group(3)
                    temp_out['offset'] = re_screen.group(4)
            except:
                pass
            out[re_screen.group(1)] = temp_out
    return out


def get_wayland_outputs():
    '''Detect connected DRM outputs from /sys/class/drm/.
    Returns list of {"name": str, "width": int, "height": int}.
    Works on Wayland systems where xrandr is unavailable.
    '''
    import os as _os
    import glob as _gglob
    outputs = []
    for d in sorted(_gglob.glob('/sys/class/drm/card*-*/')):
        try:
            status = open(d + 'status').read().strip()
        except Exception:
            continue
        if status != 'connected':
            continue
        try:
            first_mode = open(d + 'modes').readline().strip()
        except Exception:
            continue
        if not first_mode:
            continue
        connector = re.sub(r'^card\d+-', '', _os.path.basename(d.rstrip('/')))
        m = re.match(r'^(\d+)x(\d+)$', first_mode)
        if not m:
            continue
        outputs.append({
            'name': connector,
            'width': int(m.group(1)),
            'height': int(m.group(2)),
        })
    return outputs


if __name__ == '__main__':
    print(get_screens_info())
    print(get_wayland_outputs())
