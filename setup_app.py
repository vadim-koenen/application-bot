"""py2app packaging for the Job Apply Assistant desktop app.

    pip install py2app
    python3 setup_app.py py2app

Produces dist/Job Apply Assistant.app. The app bundles app_main.py + the
application_bot package + the app_ui assets. Private data (data/private, .env)
is read at runtime from the working directory, not bundled.
"""

from setuptools import setup

APP = ["app_main.py"]
DATA_FILES = [
    ("app_ui", ["app_ui/index.html"]),
    ("config", ["config/live_company_registry.yaml"]),
]
OPTIONS = {
    "argv_emulation": False,
    "packages": ["application_bot"],
    "includes": ["app_api"],
    "plist": {
        "CFBundleName": "Job Apply Assistant",
        "CFBundleIdentifier": "com.vadim.jobapply",
        "LSUIElement": False,
    },
}

setup(
    app=APP,
    name="Job Apply Assistant",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
