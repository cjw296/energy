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
Tesla scripts below, including ``octopus-tesla-sync.py`` in production. Fix it by logging
in interactively, wherever you can open a browser:

.. code-block:: bash

  uv run tesla-login.py

This opens Tesla's SSO login page and prints:

.. code-block:: text

  Enter URL after authentication:

**Do not paste the URL that was just printed/opened** — that's the login page URL, before
you've logged in, and has no ``code=`` parameter. Pasting it back gives
``oauthlib.oauth2.rfc6749.errors.MissingCodeError: (missing_code) Missing code parameter
in response``.

Instead, log in with your Tesla credentials (and MFA if enabled). Tesla's redirect URI is
now ``tesla://auth/callback``, a custom app-URI scheme a normal browser can't navigate to,
so you will *not* see the old "Page Not Found" success page. What you'll see instead is a
page that just says "Verified Successfully / Loading..." and hangs there — the browser has
tried and failed to navigate to ``tesla://auth/callback?code=...&state=...``, but the
address bar doesn't update to show it. To get that URL:

- open browser dev tools (F12) → Network tab **before** logging in (so it's already
  recording), log in, then find the failed/canceled request to ``tesla://auth/callback``
  in the list and copy its full URL, or
- copy it from an "Open in app?" dialog, if your browser shows one instead.

Paste that URL — not the original authorize URL, and not the "Verified Successfully" page's
URL — into the prompt. That refreshes
``cache.json`` in the current directory, which needs to be in place before the production
process (re)starts.

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
