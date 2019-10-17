Energy Tools
============

Environment Setup
-----------------

`Install Poetry`__ and then do a `poetry install` in a checkout of this repo.

__ https://poetry.eustace.io/docs/#installation

Then copy `config.sample.yaml` to `config.yaml` and fill in the config.

Tesla data renamer
------------------

The Tesla app has a great download facility, but it always saves files named `data.csv`.
From the app, save **daily** energy usage data somewhere that syncs (I use Dropbox).
On another machine that is synced to, run the following:

.. code-block:: bash

  python tesla-incoming.py

That will watch for arriving `data.csv` files, rename them and put them in the storage directory.

Downloading Octopus data
------------------------

This will download 30 mins consumptions readings from Octopus and put them in one csv per day
in the storage directory. You can specify a start and end date.

.. code-block:: bash

  python octopus-download.py

Reconciling Tesla data with Octopus data
----------------------------------------

This compares usage data between Tesla and Octopus where there are downloaded csvs for
the date and reports any half hours where the difference between the two exceeds the specified
threshold in kWh:

.. code-block:: bash

  python octopus-tesla-rec.py --threshold 0.2
