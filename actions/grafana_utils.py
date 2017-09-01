#!/usr/bin/python3

from charmhelpers.core.hookenv import (
    config,
    log,
)

from charmhelpers.core import unitdata


def get_admin_password():
    kv = unitdata.kv()
    if kv.get('grafana.admin_password'):
        # print('Admin password: {}'.format(kv.get('grafana.admin_password')))
        passwd = kv.get('grafana.admin_password')
    elif config('admin_password'):
        passwd = config('admin_password')
        # print('Admin password: {}'.format(config('admin_password')))
    else:
        log("Password not found!")
        passwd = None

    return passwd

