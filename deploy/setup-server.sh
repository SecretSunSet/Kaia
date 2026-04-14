#!/bin/bash
set -e

echo "=== Updating system ==="
sudo apt update && sudo apt upgrade -y

echo "=== Installing dependencies ==="
sudo apt install -y python3 python3-venv python3-pip git ffmpeg curl

echo "=== Creating app directory ==="
sudo mkdir -p /opt/kaia
sudo chown ubuntu:ubuntu /opt/kaia

echo "=== Setting up Python virtual environment ==="
cd /opt/kaia
python3 -m venv venv
source venv/bin/activate

echo "=== Cloning repository ==="
echo "Clone your repo manually:"
echo "  git clone https://github.com/YOUR_USERNAME/kaia.git app"
echo "  cd app"
echo "  pip install -r kaia/requirements.txt"
echo ""
echo "=== Then create .env ==="
echo "  cp kaia/.env.example kaia/.env"
echo "  nano kaia/.env  # fill in your API keys"
echo ""
echo "=== Then install the systemd service ==="
echo "  sudo cp deploy/kaia.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable kaia"
echo "  sudo systemctl start kaia"
