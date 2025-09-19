# Config package initialization

# Import main config to maintain backward compatibility
import sys
import os

# Add parent directory to path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import everything from main config.py file (not this package)
import importlib.util
config_path = os.path.join(parent_dir, 'config.py')
spec = importlib.util.spec_from_file_location("config_main", config_path)
config_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_main)

# Export all attributes from main config
for attr in dir(config_main):
    if not attr.startswith('_'):
        globals()[attr] = getattr(config_main, attr)

# Import SpotPlayer config
from config.spotplayer_config import spotplayer_config
