# Reproducible authoring environment

Upstream: https://github.com/kurtmckee/feedparser
Upstream commit: a22c5521cbb109871f1a2318948581901bd47e26
Verified runtime: 3.13.14 (tags/v3.13.14:fd17997, Jun 10 2026, 13:03:48) [MSC v.1944 64 bit (AMD64)]
Verified platform: win32

Use an isolated virtual environment. Install the pinned dependencies with
`python -m pip install -r requirements-domain.lock`, then `python -m pip install -e .`.
Set the following environment variables before installation and testing:

```text
PYTHONUTF8=1
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
```

Core baseline:

```text
python -m pytest -q -o addopts= tests/test_well_formed.py tests/test_ill_formed.py tests/test_json.py tests/test_parse_parameters.py
```

Measured pytest process time: 3.37 seconds on the authoring host.
Only the documented core test selection is claimed; optional integrations are outside this environment.

All documented checks use in-memory fixtures or local temporary files. No production
accounts, data services, credentials or external network endpoints are required after setup.
Reset by making a fresh checkout of this seed and creating a new virtual environment.
Test fixtures remain under their upstream repository license.
