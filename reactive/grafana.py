import os
import glob
from time import sleep
from charmhelpers import fetch
from charmhelpers.core import host, hookenv, unitdata
from charmhelpers.core.templating import render
from charmhelpers.contrib.charmsupport import nrpe
from charms.reactive import when, when_not, set_state, only_once
from charms.reactive.helpers import any_file_changed, data_changed

SVCNAME = 'grafana-server'
GRAFANA_INI = '/etc/grafana/grafana.ini'
GRAFANA_INI_TMPL = 'grafana.ini.j2'

# when
#   grafana.started
#     NO -> install and/or update -> set grafana.start
#     YES -> config-changed? restart services or else noop
#
#   grafana.start (from when_not('grafana.started')
#     NO ->
#     YES ->
#       config-changed? render or noop
#       service running?
#         no -> start
#         yes -> config-changed? -> restart
#


def install_packages():
    config = hookenv.config()
    install_opts = ('install_sources', 'install_keys')
    if not any(config.changed(opt) for opt in install_opts):
        return
    hookenv.status_set('maintenance', 'Installing deb pkgs')
    packages = ['grafana']
    fetch.configure_sources(update=True)
    fetch.apt_install(packages)
    hookenv.status_set('maintenance', 'Waiting for start')


def check_ports(new_port):
    kv = unitdata.kv()
    if kv.get('grafana.port') != new_port:
        hookenv.open_port(new_port)
        if kv.get('grafana.port'):  # Dont try to close non existing ports
            hookenv.close_port(kv.get('grafana.port'))
        kv.set('grafana.port', new_port)


@when_not('grafana.started')
def setup_grafana():
    hookenv.status_set('maintenance', 'Configuring grafana')
    install_packages()
    config = hookenv.config()
    if data_changed('grafana.config', config):
        settings = {'config': config}
        render(source=GRAFANA_INI_TMPL,
               target=GRAFANA_INI,
               context=settings,
               owner='root', group='grafana',
               perms=0o640,
               )
    check_ports(config.get('port', '3000'))
    set_state('grafana.start')
    hookenv.status_set('active', 'Ready')


@when('grafana.started')
def check_config():
    if data_changed('grafana.config', hookenv.config()):
        setup_grafana()  # reconfigure and restart
    #db_init()


@when('grafana.start')
def restart_grafana():
    if not host.service_running(SVCNAME):
        hookenv.log('Starting {}...'.format(SVCNAME))
        host.service_start(SVCNAME)
    elif any_file_changed(['/etc/grafana/grafana.ini']):
        hookenv.log('Restarting {}, config file changed...'.format(SVCNAME))
        host.service_restart(SVCNAME)
    hookenv.status_set('active', 'Ready')
    set_state('grafana.started')


@only_once
def db_init():
    sleep(10)
    check_datasources()
    check_adminuser()


@when('nrpe-external-master.available')
def update_nrpe_config(svc):
    # python-dbus is used by check_upstart_job
    fetch.apt_install('python-dbus')
    hostname = nrpe.get_nagios_hostname()
    current_unit = nrpe.get_nagios_unit_name()
    nrpe_setup = nrpe.NRPE(hostname=hostname)
    nrpe.add_init_service_checks(nrpe_setup, SVCNAME, current_unit)
    nrpe_setup.write()


@when_not('nrpe-external-master.available')
def wipe_nrpe_checks():
    checks = ['/etc/nagios/nrpe.d/check_grafana-server.cfg',
              '/var/lib/nagios/export/service__*_grafana-server.cfg']
    for check in checks:
        for f in glob.glob(check):
            if os.path.isfile(f):
                os.unlink(f)


def validate_datasources():
    """Unused. Check datasource before loading it into DB.
    """
    config = hookenv.config()

    if config.get('datasources', False):
        items = config['datasources'].split(',')
        if len(items) != 7:
            return False
        elif items[0] != 'prometheus' and items[2] != 'proxy':
            return False


def check_datasources():
    """
    CREATE TABLE `data_source` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
    , `org_id` INTEGER NOT NULL
    , `version` INTEGER NOT NULL
    , `type` TEXT NOT NULL
    , `name` TEXT NOT NULL
    , `access` TEXT NOT NULL
    , `url` TEXT NOT NULL
    , `password` TEXT NULL
    , `user` TEXT NULL
    , `database` TEXT NULL
    , `basic_auth` INTEGER NOT NULL
    , `basic_auth_user` TEXT NULL
    , `basic_auth_password` TEXT NULL
    , `is_default` INTEGER NOT NULL
    , `json_data` TEXT NULL
    , `created` DATETIME NOT NULL
    , `updated` DATETIME NOT NULL
    , `with_credentials` INTEGER NOT NULL DEFAULT 0);
    INSERT INTO "data_source" VALUES(1,1,0,'prometheus','BootStack Prometheus','proxy','http://localhost:9090','','','',0,'','',1,'{}','2016-01-22 12:11:06','2016-01-22 12:11:11',0);
    """
    try:
        import sqlite3
        import yaml
        conn = sqlite3.connect('/var/lib/grafana/grafana.db', timeout=30)
        cur = conn.cursor()
        query = cur.execute('SELECT COUNT(*) FROM DATA_SOURCE')
        rows = query.fetchone()[0]
        if rows == 0:
            config = hookenv.config()
            dss = yaml.safe_load(config['datasources'])
            hookenv.log('datasources on juju set => {}'.format(dss))
            if len(dss) > 0:
                stmt = 'INSERT INTO DATA_SOURCE (id, org_id, version'
                stmt += ', type, name, access, url, basic_auth'
                stmt += ', basic_auth_user, basic_auth_password, is_default)'
                stmt += ' VALUES (?,?,?,?,?,?,?,?,?,?,?)'
                i = 0
                isdefault = 1
                #- 'prometheus,BootStack Prometheus,proxy,http://localhost:9090,,,'
                for ds in dss:
                    ds = ds.split(',')
                    if len(ds) == 7:
                        i += 1
                        cur.execute(stmt, (i, 1, 0, ds[0], ds[1], ds[2],
                                    ds[3], ds[4], ds[5], ds[6], isdefault))
                        isdefault = 0
                if isdefault == 0:
                    conn.commit()
                    hookenv.log('[*] datasource(s) added to database')
        conn.close()
    except ImportError as e:
        hookenv.log('Could not update data_source: {}'.format(e))
    except sqlite3.OperationalError as e:
        hookenv.log('check_datasources::sqlite3.OperationError: {}'.format(e))


def check_adminuser():
    """
    CREATE TABLE `user` (
    `id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
    , `version` INTEGER NOT NULL
    , `login` TEXT NOT NULL
    , `email` TEXT NOT NULL
    , `name` TEXT NULL
    , `password` TEXT NULL
    , `salt` TEXT NULL
    , `rands` TEXT NULL
    , `company` TEXT NULL
    , `org_id` INTEGER NOT NULL
    , `is_admin` INTEGER NOT NULL
    , `email_verified` INTEGER NULL
    , `theme` TEXT NULL
    , `created` DATETIME NOT NULL
    , `updated` DATETIME NOT NULL
    );
    INSERT INTO "user" VALUES(1,0,'admin','root+bootstack-ps45@canonical.com','BootStack Team','309bc4e78bc60d02dc0371d9e9fa6bf9a809d5dc25c745b9e3f85c3ed49c6feccd4ffc96d1db922f4297663a209e93f7f2b6','LZeJ3nSdrC','hseJcLcnPN','',1,1,0,'light','2016-01-22 12:00:08','2016-01-22 12:02:13');
    """
    fetch.apt_install(['python-pbkdf2', 'python3-pbkdf2'])
    config = hookenv.config()
    passwd = config.get('admin_password', False)
    if not passwd:
        passwd = host.pwgen(16)

    try:
        import sqlite3

        stmt = "UPDATE user SET email=?, name='BootStack Team'"
        stmt += ", password=?, theme='light'"
        stmt += " WHERE id = ?"

        conn = sqlite3.connect('/var/lib/grafana/grafana.db', timeout=30)
        cur = conn.cursor()
        query = cur.execute('SELECT id, login, salt FROM user')
        for row in query.fetchall():
            if row[1] == 'admin':
                nagios_context = config.get('nagios_context', False)
                if not nagios_context:
                    nagios_context = 'UNKNOWN'
                email = 'root+%s@canonical.com' % nagios_context
                hpasswd = hpwgen(passwd, row[2])
                if hpasswd:
                    cur.execute(stmt, (email, hpasswd, row[0]))
                    conn.commit()
                    hookenv.log('[*] admin password updated on database')
                else:
                    hookenv.log('Could not update user table: hpwgen func failed')
                break
        conn.close()
    except ImportError as e:
        hookenv.log('Could not update user table: {}'.format(e))
        return
    except sqlite3.OperationalError as e:
        hookenv.log('check_adminuser::sqlite3.OperationError: {}'.format(e))
        return


def hpwgen(passwd, salt):
    try:
        import pbkdf2
        import hashlib
        hpasswd = pbkdf2.PBKDF2(passwd, salt, 10000, hashlib.sha256).hexread(50)
        return hpasswd
    except ImportError as e:
        hookenv.log('Could not generate PBKDF2 hashed password: {}'.format(e))
        return
