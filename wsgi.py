import sys
import os

# Add project directory to sys.path so PythonAnywhere can find modules
project_folder = os.path.dirname(__file__)
if project_folder not in sys.path:
    sys.path.insert(0, project_folder)

from web_app import app as application
