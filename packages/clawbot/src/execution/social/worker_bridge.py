"""
Social Worker Bridge — standalone wrapper around social_browser_worker.py

Direct extraction of ExecutionHub._run_social_worker() (execution_hub.py:1491-1540),
decoupled from the class instance so that the RPC layer (and any other caller)
can invoke the browser worker without needing an ExecutionHub object.
"""
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# packages/clawbot/  (four parents up from this file)
#   this file:  packages/clawbot/src/execution/social/worker_bridge.py
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def run_social_worker(
    action: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run scripts/social_browser_worker.py as a subprocess and return parsed JSON.

    Mirrors ExecutionHub._run_social_worker() exactly:
      - 2 retries for publish actions, 1 attempt for everything else
      - 300-second timeout
      - JSON stdout parsing with setdefault("success", True)
      - 3-second sleep between retries

    Args:
        action:  The worker action string (e.g. "publish_x", "publish_xhs", "status").
        payload: Arbitrary dict serialised as JSON and passed as the second CLI arg.

    Returns:
        dict with at least a ``success`` key.
    """
    worker = _PACKAGE_ROOT / "scripts" / "social_browser_worker.py"
    payload = payload or {}
    max_retries = 2 if action and "publish" in str(action) else 1
    last_err: Optional[Dict[str, Any]] = None

    for attempt in range(max_retries):
        try:
            # 状态查询用短超时（5秒），发布等操作用长超时（300秒）
            timeout_sec = 5 if action == "status" else 300
            cp = subprocess.run(
                [
                    "python3",
                    str(worker),
                    action,
                    json.dumps(payload, ensure_ascii=False),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )

            if cp.returncode != 0:
                last_err = {
                    "success": False,
                    "error": "worker exited {}".format(cp.returncode),
                    "stderr": str(cp.stderr or "").strip(),
                    "stdout": str(cp.stdout or "").strip(),
                }
                if attempt < max_retries - 1:
                    logger.warning(
                        "[SocialWorker] %s 失败(attempt %d)，重试中...",
                        action,
                        attempt + 1,
                    )
                    time.sleep(3)
                    continue
                return last_err

            stdout = str(cp.stdout or "").strip()
            if not stdout:
                last_err = {
                    "success": False,
                    "error": "worker produced no output",
                }
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
                return last_err

            data = json.loads(stdout)
            if isinstance(data, dict):
                data.setdefault("success", True)
                return data
            return {"success": False, "error": "worker 输出不是对象"}

        except subprocess.TimeoutExpired:
            last_err = {"success": False, "error": f"worker 超时 (action={action})"}
            logger.warning(
                "[SocialWorker] %s 超时(attempt %d)", action, attempt + 1
            )
        except json.JSONDecodeError as e:
            last_err = {"success": False, "error": f"worker 输出解析失败: {e}"}
            logger.warning(
                "[SocialWorker] %s JSON解析失败: %s", action, e
            )
        except Exception as e:
            last_err = {"success": False, "error": str(e)}
            logger.warning(
                "[SocialWorker] %s 异常(attempt %d): %s", action, attempt + 1, e
            )

        if attempt < max_retries - 1:
            time.sleep(3)

    return last_err or {"success": False, "error": "unknown"}


async def run_social_worker_async(
    action: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """异步版本 run_social_worker — 不阻塞事件循环。

    与同步版本逻辑完全一致，但使用 asyncio.create_subprocess_exec 和 asyncio.sleep。
    """
    import asyncio
    worker = _PACKAGE_ROOT / "scripts" / "social_browser_worker.py"
    payload = payload or {}
    max_retries = 2 if action and "publish" in str(action) else 1
    last_err: Optional[Dict[str, Any]] = None

    for attempt in range(max_retries):
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", str(worker), action,
                json.dumps(payload, ensure_ascii=False),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=300
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                last_err = {"success": False, "error": f"worker 超时 (action={action})"}
                logger.warning("[SocialWorker] %s 超时(attempt %d)", action, attempt + 1)
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)
                continue

            stdout = (stdout_bytes or b"").decode().strip()
            stderr = (stderr_bytes or b"").decode().strip()

            if proc.returncode != 0:
                last_err = {"success": False, "error": f"worker exited {proc.returncode}",
                            "stderr": stderr, "stdout": stdout}
                if attempt < max_retries - 1:
                    logger.warning("[SocialWorker] %s 失败(attempt %d)，重试中...", action, attempt + 1)
                    await asyncio.sleep(3)
                    continue
                return last_err

            if not stdout:
                last_err = {"success": False, "error": "worker produced no output"}
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)
                    continue
                return last_err

            data = json.loads(stdout)
            if isinstance(data, dict):
                data.setdefault("success", True)
                return data
            return {"success": False, "error": "worker 输出不是对象"}

        except json.JSONDecodeError as e:
            last_err = {"success": False, "error": f"worker 输出解析失败: {e}"}
            logger.warning("[SocialWorker] %s JSON解析失败: %s", action, e)
        except Exception as e:
            last_err = {"success": False, "error": str(e)}
            logger.warning("[SocialWorker] %s 异常(attempt %d): %s", action, attempt + 1, e)

        if attempt < max_retries - 1:
            await asyncio.sleep(3)

    return last_err or {"success": False, "error": "unknown"}
