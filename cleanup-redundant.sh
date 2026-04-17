#!/bin/bash
# 清理冗余的 OpenClaw 目录

echo "=========================================="
echo "清理 OpenEverything 冗余目录"
echo "=========================================="
echo ""

cd /Users/blackdj/Desktop/OpenEverything

echo "正在删除冗余目录..."
echo ""

if [ -d "OpenClaw_2026-04-17_20-22-26" ]; then
    echo "  删除 OpenClaw_2026-04-17_20-22-26 (43MB)..."
    sudo rm -rf OpenClaw_2026-04-17_20-22-26
    if [ $? -eq 0 ]; then
        echo "  ✅ 已删除"
    else
        echo "  ❌ 删除失败"
    fi
fi

if [ -d "OpenClaw_2026-04-17_20-23-02" ]; then
    echo "  删除 OpenClaw_2026-04-17_20-23-02 (1.4MB)..."
    sudo rm -rf OpenClaw_2026-04-17_20-23-02
    if [ $? -eq 0 ]; then
        echo "  ✅ 已删除"
    else
        echo "  ❌ 删除失败"
    fi
fi

echo ""
echo "=========================================="
echo "✅ 清理完成！"
echo "=========================================="
echo ""
echo "当前目录结构："
ls -lh
