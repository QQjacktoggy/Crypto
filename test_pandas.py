import sys
import subprocess

def check_package_versions():
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas-ta==0.3.14b0"])

check_package_versions()
