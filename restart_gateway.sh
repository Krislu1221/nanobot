#!/bin/bash
cd /Users/krislu/nanobot
source venv/bin/activate
nohup Nanobot gateway --port 18799 > ~/.nanobot/logs/猫王-gateway.log 2>&1 &
echo "Gateway started with PID: $!"
