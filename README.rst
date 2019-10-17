Energy Tools
============

Environment Setup
-----------------

`Install Poetry`__ and then do a `poetry install` in a checkout of this repo.

https://poetry.eustace.io/docs/#installation

Then copy `config.sample.yaml` to `config.yaml` and fill in the config.

Tesla Data Renamer
------------------

The Tesla app has a great download facility, but it always saves files named `data.csv`.
From the app, save **daily** energy usage data somewhere that syncs (I use Dropbox).
On another machine that is synced to, run the following:

.. code-block:: bash

  python tesla-incoming.py

That will watch for arriving `data.csv` files, rename them and put them in the storage directory.
