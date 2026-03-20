#!/usr/bin/env python3
"""
ClawBot 全链路诊断脚本 — 逐阶段验证交易管道
用法: source .venv/bin/activate && python scripts/diagnose_pipeline.py

阶段:
  1. 全市场扫描 (600+ 标的)
  2. 候选过滤 (_filter_candidates)
  3. 技术分析 (get_full_analysis)
  4. AI 团队投票 (单个 caller 测试)
  5. 风控审核 (DecisionValidator + RiskManager)
  6. IBKR 连接检查
"""
import asyncio
import json
import logging
import os
import sys
import time

# 确保项目根目录在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv("config/.env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("diagnose")


def sep(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


async def stage1_scan():
    """阶段1: 全市场扫描"""
    sep("阶段 1: 全市场扫描")
    try:
        from src.universe import full_market_scan
        t0 = time.time()
        result = await full_market_scan()
        elapsed = time.time() - t0

        total = result.get("total_scanned", 0)
        l1 = result.get("layer1_passed", 0)
        l2 = result.get("layer2_passed", 0)
        candidates = result.get("top_candidates", [])

        print(f"  扫描标的: {total}")
        print(f"  层1通过: {l1}")
        print(f"  层2通过: {l2}")
        print(f"  Top候选: {len(candidates)}")
        print(f"  耗时: {elapsed:.1f}s")

        if candidates:
            print("\n  Top 10 候选:")
            for i, c in enumerate(candidates[:10]):
                print(
                    f"    {i+1}. {c.get('symbol','?'):6s} "
                    f"${c.get('price',0):>8.2f} "
                    f"score={c.get('score',0):+4d} "
                    f"trend={c.get('trend','?'):12s} "
                    f"RSI6={c.get('rsi_6',0):.0f} "
                    f"ADX={c.get('adx',0):.0f} "
                    f"vol_avg={c.get('vol_avg_20',0):,.0f}"
                )
        else:
            print("  [警告] 无候选标的!")

        return candidates
    except Exception as e:
        print(f"  [错误] 扫描失败: {e}")
        import traceback; traceback.print_exc()
        return []


async def stage2_filter(candidates):
    """阶段2: 候选过滤"""
    sep("阶段 2: 候选过滤 (_filter_candidates)")
    try:
        from src.auto_trader import AutoTrader
        trader = AutoTrader()
        filtered = trader._filter_candidates(candidates)

        print(f"  输入: {len(candidates)} 个候选")
        print(f"  通过: {len(filtered)} 个")

        if filtered:
            print("\n  通过筛选的候选:")
            for i, c in enumerate(filtered[:10]):
                print(
                    f"    {i+1}. {c.get('symbol','?'):6s} "
                    f"score={c.get('score',0):+4d} "
                    f"trend={c.get('trend','?'):12s} "
                    f"RSI6={c.get('rsi_6',0):.0f} "
                    f"ADX={c.get('adx',0):.0f} "
                    f"vol_avg={c.get('vol_avg_20',0):,.0f}"
                )
        else:
            print("  [警告] 全部被过滤! 检查过滤条件是否过严")
            # 打印被淘汰的原因分布
            from src.auto_trader import AutoTrader as AT2
            t2 = AT2()
            print("\n  被淘汰原因分析:")
            reasons = {"score<20": 0, "strong_down": 0, "rsi>80": 0, "price<3": 0, "vol<100k": 0, "adx<15": 0, "passed": 0}
            for s in candidates:
                score = s.get("score", 0)
                if score < 20:
                    reasons["score<20"] += 1; continue
                trend = s.get("trend", "sideways")
                if trend == "strong_down":
                    reasons["strong_down"] += 1; continue
                rsi6 = s.get("rsi_6", 50)
                if rsi6 > 80:
                    reasons["rsi>80"] += 1; continue
                price = s.get("price", 0)
                if 0 < price < 3:
                    reasons["price<3"] += 1; continue
                vol_avg = s.get("vol_avg_20", 0)
                if 0 < vol_avg < 100_000:
                    reasons["vol<100k"] += 1; continue
                adx = s.get("adx", 0)
                if 0 < adx < 15:
                    reasons["adx<15"] += 1; continue
                reasons["passed"] += 1
            for k, v in reasons.items():
                if v > 0:
                    print(f"    {k}: {v}")

        return filtered
    except Exception as e:
        print(f"  [错误] 过滤失败: {e}")
        import traceback; traceback.print_exc()
        return []


async def stage3_analysis(candidates):
    """阶段3: 技术分析"""
    sep("阶段 3: 技术分析 (get_full_analysis)")
    if not candidates:
        print("  [跳过] 无候选标的")
        return {}

    try:
        from src.ta_engine import get_full_analysis
        # 只分析前3个
        analyses = {}
        for c in candidates[:3]:
            sym = c.get("symbol", "")
            try:
                t0 = time.time()
                data = await get_full_analysis(sym)
                elapsed = time.time() - t0
                if isinstance(data, dict) and "error" not in data:
                    analyses[sym] = data
                    print(f"  {sym}: OK ({elapsed:.1f}s) - price=${data.get('price',0):.2f}, RSI={data.get('rsi',0):.0f}")
                else:
                    print(f"  {sym}: 失败 - {data}")
            except Exception as e:
                print(f"  {sym}: 异常 - {e}")
        return analyses
    except Exception as e:
        print(f"  [错误] 分析模块加载失败: {e}")
        return {}


async def stage4_ai_caller():
    """阶段4: AI Caller 测试"""
    sep("阶段 4: AI Caller 连通性测试")

    # 测试 g4f (Qwen)
    print("\n  测试 g4f (端口 18891)...")
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": "qwen-3-235b",
                "messages": [{"role": "user", "content": "Say OK in one word"}],
                "max_tokens": 10,
            }
            async with session.post(
                "http://localhost:18891/v1/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    print(f"    g4f/Qwen: OK - 回复: {reply[:50]}")
                else:
                    text = await resp.text()
                    print(f"    g4f/Qwen: HTTP {resp.status} - {text[:100]}")
    except Exception as e:
        print(f"    g4f/Qwen: 失败 - {e}")

    # 测试 Kiro Gateway (Claude)
    print("\n  测试 Kiro Gateway (端口 18793)...")
    try:
        kiro_key = os.environ.get("KIRO_API_KEY", "")
        if not kiro_key:
            # 尝试从 .env 读取
            kiro_key = os.environ.get("CLAUDE_API_KEY", "")
        if not kiro_key:
            print("    Kiro: 跳过 - 无 API Key")
        else:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "claude-haiku-4.5",
                    "messages": [{"role": "user", "content": "Say OK in one word"}],
                    "max_tokens": 10,
                }
                headers = {"Authorization": f"Bearer {kiro_key}"}
                async with session.post(
                    "http://localhost:18793/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        print(f"    Kiro/Claude: OK - 回复: {reply[:50]}")
                    else:
                        text = await resp.text()
                        print(f"    Kiro/Claude: HTTP {resp.status} - {text[:100]}")
    except Exception as e:
        print(f"    Kiro/Claude: 失败 - {e}")


async def stage5_risk_check(candidates):
    """阶段5: 风控检查"""
    sep("阶段 5: 风控审核")
    if not candidates:
        print("  [跳过] 无候选标的")
        return

    try:
        from src.risk_manager import RiskManager, RiskConfig
        config = RiskConfig(total_capital=2000.0)
        rm = RiskManager(config)

        c = candidates[0]
        sym = c.get("symbol", "TEST")
        price = c.get("price", 100)
        stop = round(price * 0.97, 2)
        target = round(price * 1.06, 2)
        qty = max(1, int(400 / price))

        check = rm.check_trade(
            symbol=sym, side="BUY", quantity=qty,
            entry_price=price, stop_loss=stop, take_profit=target,
            current_positions=[],
        )
        print(f"  标的: {sym} x{qty} @ ${price:.2f}")
        print(f"  止损: ${stop:.2f} | 止盈: ${target:.2f}")
        print(f"  风控结果: {'通过' if check.get('approved') else '拒绝'}")
        if not check.get("approved"):
            print(f"  拒绝原因: {check.get('reason', '?')}")
        if check.get("warnings"):
            print(f"  警告: {check['warnings']}")
    except Exception as e:
        print(f"  [错误] 风控检查失败: {e}")
        import traceback; traceback.print_exc()


async def stage6_ibkr():
    """阶段6: IBKR 连接检查"""
    sep("阶段 6: IBKR 连接检查")
    try:
        from src.broker_bridge import IBKRBridge
        bridge = IBKRBridge()
        connected = await bridge.ensure_connected()
        if connected:
            print(f"  IBKR: 已连接")
            print(f"  账户: {bridge.account}")
            print(f"  预算: ${bridge.budget:.2f}")
            print(f"  已花费: ${bridge.total_spent:.2f}")
            # 获取持仓
            try:
                positions = await bridge.get_positions()
                print(f"  持仓: {len(positions)} 笔")
                for p in positions:
                    print(f"    {p}")
            except Exception as e:
                print(f"  获取持仓失败: {e}")
        else:
            print("  IBKR: 未连接 (IB Gateway 是否运行?)")
            print("  [提示] 交易将以模拟模式运行，不会实际下单")
    except Exception as e:
        print(f"  [错误] IBKR 检查失败: {e}")


async def main():
    print("\n" + "#" * 60)
    print("#  ClawBot 全链路诊断")
    print("#  " + time.strftime("%Y-%m-%d %H:%M:%S"))
    print("#" * 60)

    # 阶段1: 扫描
    candidates = await stage1_scan()

    # 阶段2: 过滤
    filtered = await stage2_filter(candidates)

    # 阶段3: 技术分析
    analyses = await stage3_analysis(filtered)

    # 阶段4: AI Caller
    await stage4_ai_caller()

    # 阶段5: 风控
    await stage5_risk_check(filtered)

    # 阶段6: IBKR
    await stage6_ibkr()

    # 总结
    sep("诊断总结")
    print(f"  扫描候选: {len(candidates)}")
    print(f"  过滤通过: {len(filtered)}")
    print(f"  分析成功: {len(analyses)}")
    if len(filtered) > 0 and len(analyses) > 0:
        print("\n  [结论] 管道基本畅通，交易时段内应能正常执行")
    elif len(filtered) == 0:
        print("\n  [结论] 过滤后无候选! 需要进一步放宽条件或检查市场状态")
    else:
        print("\n  [结论] 部分阶段有问题，请检查上方错误信息")


if __name__ == "__main__":
    asyncio.run(main())
