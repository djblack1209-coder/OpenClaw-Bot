#!/bin/bash
set -e
# 关闭现有swap
swapoff /swapfile
# 重建4G swap
dd if=/dev/zero of=/swapfile bs=1M count=4096 status=progress
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo "Swap resized to 4GB:"
free -h
