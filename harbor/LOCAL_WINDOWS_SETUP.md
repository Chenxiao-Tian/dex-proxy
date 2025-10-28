# Harbor Dex Proxy Windows Setup Guide

This guide explains how to prepare the **Harbor** connector inside the `dex-proxy` repository on a Windows workstation.  It assumes the repository lives at `C:\Users\92585\新建文件夹 (2)\dex-proxy` and that you already have Python 3.11 (or newer) installed.

## 1. Make sure your local checkout includes the Harbor files

1. Open **PowerShell** and change into the repository root:

   ```powershell
   cd "C:\Users\92585\新建文件夹 (2)\dex-proxy"
   ```

2. Synchronise with the upstream repository so the Harbor integration is present:

   ```powershell
   git fetch origin
   git checkout main   # or the integration branch provided by Auros
   git pull --ff-only
   ```

3. (Optional) Create a dedicated branch for your Harbor work before committing changes back to the corporate repository:

   ```powershell
   git checkout -b harbor-integration
   git push -u origin harbor-integration
   ```

   The second command publishes the branch to your remote so reviewers can see the Harbor code.  If your company uses a
   different branch name, adjust it accordingly.

4. Confirm that the Harbor package exists by listing the `harbor` directory:

   ```powershell
   dir harbor
   ```

   The command should display a structure that includes the `dex_proxy` package.  If the folder still does not exist, double-check that your Git remote points to the correct Auros repository (`git remote -v`) or contact Jakku/Mark for the branch name that contains the Harbor integration.

With a current checkout you should see the following layout:

```
C:\Users\92585\新建文件夹 (2)\dex-proxy\harbor\dex_proxy\
    __init__.py
    harbor.py
    harbor_api.py
    main.py
```

You do **not** need to move files around.  `harbor.py` contains the `DexCommon` implementation and must remain under `harbor/dex_proxy/harbor.py` so that Python can import it as `harbor.dex_proxy.harbor`.

The configuration file that drives the service lives here:

```
C:\Users\92585\新建文件夹 (2)\dex-proxy\harbor\harbor.config.json
```

## 2. Create and activate a virtual environment

Open **PowerShell** and run the following commands:

```powershell
cd "C:\Users\92585\新建文件夹 (2)\dex-proxy\harbor"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

This installs the Harbor package (and its dependencies) in an isolated environment.

> If your corporate PowerShell execution policy blocks script execution, start PowerShell *as Administrator* and run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once, then retry the activation command.

## 3. Provide Harbor credentials

The connector can read API keys directly from the environment or from the config file.  The simplest approach is to export them in the shell session before launching the proxy.

```powershell
$env:HARBOR_API_KEY = '6c30c576-f7db-4ae5-ac19-118d456c082e'
$env:ETH_FROM_ADDR = '0xD1287859F3197C05c67578E3d64092e6639b1000'
$env:BTC_FROM_ADDR = 'bc1qu5s2s97g0s0a0pnhe7h2jxj0aexue8u6wjgxsj'
```

Alternatively, you can hard-code these values in `harbor.config.json` under `dex.connectors.harbor` by adding `api_key`, `eth_from_addr`, and `btc_from_addr` fields, but environment variables keep secrets out of version control.

## 4. Launch the Harbor proxy

From the same activated virtual environment run:

```powershell
python -u -m harbor.dex_proxy.main -s -c harbor.config.json -n harbor
```

* `-s` tells Pantheon to start services immediately.
* `-c harbor.config.json` loads the Harbor specific configuration file.
* `-n harbor` registers the service under the "harbor" namespace.

The web server will start on port `7158` as defined in the config.  After the log messages settle, open http://localhost:7158/docs in a browser to explore the OpenAPI UI.

## 5. Verifying connectivity

1. Call the **`/dex/account`** endpoint from the docs UI; with the provided API key the response should be `{}` until funds are deposited.
2. Fetch market metadata from **`/dex/markets`** to confirm the connector can reach Harbor.
3. (Optional) Use the `/dex/order` endpoints to place test orders once your Harbor account holds balances.

## 6. Stopping the service

Press `Ctrl+C` in the PowerShell window.  The Dex Proxy shuts down gracefully and closes the Harbor HTTP session automatically.

## 7. Reusing the environment

Future sessions only require steps 2 (activate the venv), 3 (export credentials), and 4 (run the proxy).  There is no need to recreate the environment unless dependencies change.

## 8. Optional: running the Harbor unit tests

If you install the testing extras (`python -m pip install -e .[tests]`) and have `pytest` available, the connector tests live under `harbor/tests/`.  From the Harbor directory:

```powershell
pytest harbor/tests -q
```

Make sure `aiohttp` and any system-level dependencies are available before running the tests.
