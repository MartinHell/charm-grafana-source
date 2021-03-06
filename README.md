#Overview

This charm provides the latest stable version of Grafana.

#Usage

    juju deploy grafana
    juju add-relation prometheus:grafana-source grafana:grafana-source

Above will automatically configure prometheus as grafana datasource

If admin password is not set using configuration option it is autogenerated.
To retrieve autogenerated password run:
    $ juju run-action --wait grafana/0 get-admin-password


#Actions

This charm supports importing dashboards, simply run:

 $ juju run-action --wait grafana/0 import-dashboard dashboard="$(base64 mydashboard.json)"

where mydashboard.json is a json file:

 { "dashboard": { exported-json-dashboard },
   "overwrite": true }

If you don't want to overwrite the dashboard, set overwrite to false.

There is also an action to create an API key, run:

 $ juju run-action --wait grafana/0 create-api-key keyname=<name> keyrole=<role>

where the keyrole is one of Viewer, Editor, Read Only Editor or Admin.

You can also retrieve the admin password, via:

 $ juju run-action --wait grafana/0 get-admin-password

#Development

Explicitly set `JUJU_REPOSITORY`:

    export JUJU_REPOSITORY=/path/to/charms
    mkdir -p $JUJU_REPOSITORY/layers

Branch code to

    $JUJU_REPOSITORY/layers/layer-grafana/

Modify

Assemble the charm:

    charm build

#Contact Information

Author: Alvaro Uria <alvaro.uria@canonical.com>, Jacek Nykis <jacek.nykis@canonical.com>
Report bugs at: https://bugs.launchpad.net/charms/+source/grafana
Location:
  Composed grafana charm: cs:~prometheus-charmers/grafana
  Grafana layer: https://code.launchpad.net/grafana-charm
