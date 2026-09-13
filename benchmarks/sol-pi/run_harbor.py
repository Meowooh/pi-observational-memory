"""Keep Harbor's local cache in the authorized workspace without changing HOME."""
import os
from pathlib import Path
import harbor.constants as constants

original = constants.CACHE_DIR
relocated = Path(os.environ["OM_BENCH_HARBOR_CACHE"]).resolve()
for name, value in list(vars(constants).items()):
    if isinstance(value, Path) and value.is_relative_to(original):
        setattr(constants, name, relocated / value.relative_to(original))

from harbor.cli.main import app
app()
