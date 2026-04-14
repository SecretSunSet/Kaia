#!/bin/bash
set -e
cd /opt/kaia/app
git pull origin main
source /opt/kaia/venv/bin/activate
pip install -r kaia/requirements.txt --quiet
sudo systemctl restart kaia
echo "KAIA updated and restarted"
sudo systemctl status kaia --no-pager
