import os
import sys

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, parent_dir)

from dex_proxy_common_setup import setup


setup([
    "aiohttp>=3.8.1",
    "pantheon>=2.0.0",
])
