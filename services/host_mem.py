"""宿主机物理内存读取与鹊桥口径修正。

鹊桥 `get_status` 的 ``physical_memory`` 口径为 ``used = total - free``
（把 page cache 计入 used），容器/高缓存机器上会常年显示接近 100%。
本插件只能拿到鹊桥给的 total/free/used/percentage，**没有 MemAvailable 口径
数据**，因此无法在任意部署下还原「排除可回收缓存的真实使用」：

- 同机部署（鹊桥读到的 MemTotal 与本机一致，±5%）：用 ``/proc/meminfo``
  的 ``MemAvailable`` 口径修正 used/free/percentage，面板显示真实可用
- 跨机部署（MemTotal 不匹配）：本机 meminfo 是另一台机器，无法修正远端
  口径，物理内存字段清零——面板只保留 JVM 堆内存（进程内数据，跨机可信）
- 读取失败（非 Linux / 文件不可读）：Windows 上鹊桥读的是可用物理内存
  （含可回收 standby，无页缓存虚高问题），保留原值；其余平台无法判定，
  清零隐藏
"""

import os
from typing import Any


def read_host_meminfo() -> dict[str, int] | None:
    """读本机 ``/proc/meminfo`` 的 MemTotal/MemAvailable（字节）；失败返回 None。

    仅 Linux 有效；非 Linux 平台（open 失败）或字段缺失时返回 None，
    由调用方按「无法判定」处理。
    """
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            values: dict[str, int] = {}
            for line in f:
                if line.startswith(("MemTotal:", "MemAvailable:")):
                    key, rest = line.split(":", 1)
                    values[key] = int(rest.strip().split()[0]) * 1024  # kB → bytes
        if "MemTotal" in values and "MemAvailable" in values:
            return values
    except (OSError, ValueError, IndexError):
        pass
    return None


def correct_physical_memory(
    status: dict[str, Any],
    host_mem: dict[str, int] | None = None,
) -> dict[str, Any]:
    """按部署形态修正物理内存（原地修改并返回）。

    入参出参均为 ``ServerStatus.to_dict()`` 的结果；``host_mem`` 供测试注入
    固定值，缺省时读取本机 ``/proc/meminfo``。

    同机判定：鹊桥 ``memory_total`` 与本机 MemTotal 相差 ≤5%。
    - 同机：``memory_used`` = MemTotal - MemAvailable（排除可回收 page
      cache），``memory_free`` = MemAvailable，percentage/usage_text 同步重算
    - 跨机：物理内存字段清零（``usage_text`` 置「未知」），面板只保留 JVM
      堆内存，避免显示误导性的「常年接近满」
    - 读不到 meminfo：Windows 上鹊桥口径本身无页缓存虚高（读的是可用
      物理内存），保留原值；其余平台清零隐藏
    """
    mem = host_mem if host_mem is not None else read_host_meminfo()
    if not mem:
        # Windows：鹊桥 used = total - 可用物理内存（含可回收 standby），
        # 无 Linux MemFree 的页缓存虚高问题，保留原值展示
        if os.name == "nt":
            return status
        return _hide_physical(status)
    total = status.get("memory_total")
    if not isinstance(total, int) or total <= 0:
        return status
    if abs(total - mem["MemTotal"]) / mem["MemTotal"] > 0.05:
        # 跨机部署：本机 meminfo 是另一台机器，无法修正远端口径
        return _hide_physical(status)

    used = mem["MemTotal"] - mem["MemAvailable"]
    pct = used / mem["MemTotal"] * 100
    status["memory_used"] = used
    status["memory_free"] = mem["MemAvailable"]
    status["memory_percentage"] = round(pct, 2)
    status["memory_usage_text"] = (
        f"{used / 1024 / 1024:.1f}MB / {mem['MemTotal'] / 1024 / 1024:.1f}MB"
        f" ({pct:.1f}%)"
    )
    return status


def _hide_physical(status: dict[str, Any]) -> dict[str, Any]:
    """清零物理内存字段：面板与文本输出不再展示，仅保留 JVM 堆内存。"""
    status["memory_total"] = 0
    status["memory_used"] = 0
    status["memory_free"] = 0
    status["memory_percentage"] = 0.0
    status["memory_usage_text"] = "未知"
    return status
