Energy Tools
============

Environment Setup
-----------------

```
uv sync
```

Then copy ``config.sample.yaml`` to ``config.yaml`` and fill in the config.

Tesla login
-----------

Tesla's SSO refresh token occasionally gets invalidated (Tesla-side revocation, not
something this codebase controls), which shows up as ``LoginRequired`` from any of the
Tesla scripts below, including ``octopus-tesla-sync.py`` in production. Tesla also changed
their SSO redirect URI to ``tesla://auth/callback``, a custom app-URI scheme a normal
browser can't navigate to, which broke teslapy's own browser-based login flow. So logging
in goes via `tesla_auth <https://github.com/adriankumpf/tesla_auth>`_ instead, a small
native app that handles that redirect (and MFA/captcha) for you:

1. Install ``tesla_auth`` — download a prebuilt binary for your platform from its
   `releases page <https://github.com/adriankumpf/tesla_auth/releases/latest>`_ and put it
   on your ``PATH``. On Linux this also needs WebKitGTK and ``libxdo``; see its README.
2. Run:

   .. code-block:: bash

     uv run tesla-login.py

   This launches ``tesla_auth``. Log in with your Tesla credentials (and MFA if enabled);
   its final window shows the refresh token — copy it and paste it in when prompted.

That refreshes ``cache.json`` in the current directory, which needs to be in place before
the production process (re)starts. This needs wherever you run it to have a display, so it
can't be done directly on a headless production host.

Tesla data renamer
------------------

The Tesla app has a great download facility, but it always saves files named ``data.csv``.
From the app, save **daily** energy usage data somewhere that syncs (I use Dropbox).
On another machine that is synced to, run the following:

.. code-block:: bash

  uv run tesla-incoming.py

That will watch for arriving ``data.csv`` files, rename them and put them in the storage directory.

Downloading Octopus data
------------------------

This will download 30 mins consumptions readings from Octopus and put them in one csv per day
in the storage directory. You can specify a start and end date.

.. code-block:: bash

  uv run octopus-download.py

Reconciling Tesla data with Octopus data
----------------------------------------

This compares usage data between Tesla and Octopus where there are downloaded csvs for
the date and reports any half hours where the difference between the two exceeds the specified
threshold in kWh:

.. code-block:: bash

  uv run octopus-tesla-rec.py --threshold 0.2

Octopus Bill Calculator for Go
------------------------------

This calculates your bill based on the data downloaded above. So, for October's bill, as an
example, you'd do:

.. code-block:: bash

  uv run octopus-bill.py 2019-10-01 2019-11-01
