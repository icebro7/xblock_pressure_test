import os
import sys
import json
import time
from typing import Any, Dict, List, Optional, Tuple

# 允许从项目根导入
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 复用现有的地址获取实现
from recharge.getAddress import (
    get_recharge_address_json,
    batch_get_recharge_address_json,
)


def extract_addresses_from_json(resp_json: Dict[str, Any]) -> List[str]:
    """从地址接口的 JSON 中尽量解析地址列表。
    兼容形态：
    - {"data": "0x..."}
    - {"data": {"address": "0x..."}}
    - {"data": {"addresses": ["0x...", ...]}}
    - {"data": {"list": [{"address": "0x..."}, ...]}}
    - 直接为字符串 "0x..."
    """
    candidates: List[str] = []

    def add_if_addr(s: Any):
        if isinstance(s, str):
            s2 = s.strip()
            if s2 and s2.startswith('0x') and len(s2) >= 42:
                candidates.append(s2)

    root = resp_json if resp_json is not None else {}

    if isinstance(root, str):
        add_if_addr(root)

    data = root.get('data', root) if isinstance(root, dict) else root

    if isinstance(data, str):
        add_if_addr(data)

    if isinstance(data, dict):
        add_if_addr(data.get('address'))
        addrs_arr = data.get('addresses')
        if isinstance(addrs_arr, list):
            for a in addrs_arr:
                add_if_addr(a)
        lst = data.get('list')
        if isinstance(lst, list):
            for item in lst:
                if isinstance(item, dict):
                    add_if_addr(item.get('address'))

    seen = set()
    uniq: List[str] = []
    for a in candidates:
        if a not in seen:
            seen.add(a)
            uniq.append(a)
    return uniq


def fetch_single_address(lock_time: Optional[int] = None,
                         chain_name: Optional[str] = None,
                         wallet_id: Optional[int] = None) -> List[str]:
    """获取一次充值地址，解析后返回地址列表（可能 0/1/N 个）。"""
    resp = get_recharge_address_json(lock_time=lock_time, chain_name=chain_name, wallet_id=wallet_id)
    return extract_addresses_from_json(resp)


def run_address_stress(total: int,
                       max_workers: Optional[int] = None,
                       lock_time: Optional[int] = None,
                       chain_name: Optional[str] = None,
                       wallet_id: Optional[int] = None) -> Dict[str, Any]:
    """并发批量获取充值地址的压测函数（单次批量）。

    Args:
        total: 本轮并发请求总量（同参数重复请求 total 次）
        max_workers: 线程池并发度；若不传则使用环境变量 GETADDR_MAX_WORKERS 或默认 1
        lock_time, chain_name, wallet_id: 透传给地址接口

    Returns:
        一个结果字典：{
          "success": int,
          "failed": int,
          "sample_addresses": List[str],
          "errors": List[dict],
        }
    """
    if max_workers is not None:
        os.environ['GETADDR_MAX_WORKERS'] = str(max_workers)

    success_list, fail_list = batch_get_recharge_address_json(
        total=total,
        lock_time=str(lock_time) if lock_time is not None else None,
        chain_name=chain_name,
        wallet_id=str(wallet_id) if wallet_id is not None else None,
    )

    # 从部分成功样本解析地址
    sample_addresses: List[str] = []
    for item in success_list[:10]:  # 仅取前 10 条做样本
        sample_addresses.extend(extract_addresses_from_json(item))
    # 去重
    seen = set()
    sample_addresses = [a for a in sample_addresses if not (a in seen or seen.add(a))]

    result = {
        "success": len(success_list),
        "failed": len(fail_list),
        "sample_addresses": sample_addresses,
        "errors": fail_list[:10],  # 返回前 10 个错误样本
    }
    return result


def run_address_stress_fixed(qps: int,
                             duration_sec: int,
                             lock_time: Optional[int] = None,
                             chain_name: Optional[str] = None,
                             wallet_id: Optional[int] = None) -> Dict[str, Any]:
    """固定并发(近似固定QPS)的地址获取压测，按秒循环执行。

    每秒会以并发度=qps 发送 qps 个请求，如果耗时不足 1s，会补齐睡眠至 1s。
    返回逐秒统计、总成功/失败以及样本地址。
    """
    if qps <= 0 or duration_sec <= 0:
        raise ValueError('qps 和 duration_sec 必须为正整数')

    total_success = 0
    total_failed = 0
    per_sec: List[Dict[str, Any]] = []
    sample_addresses: List[str] = []

    for sec in range(duration_sec):
        print(f'\n⏱️ 第 {sec+1}/{duration_sec} 秒 - 目标并发 {qps}')
        os.environ['GETADDR_MAX_WORKERS'] = str(qps)
        t0 = time.time()
        success_list, fail_list = batch_get_recharge_address_json(
            total=qps,
            lock_time=str(lock_time) if lock_time is not None else None,
            chain_name=chain_name,
            wallet_id=str(wallet_id) if wallet_id is not None else None,
        )
        dt = time.time() - t0
        s_cnt = len(success_list)
        f_cnt = len(fail_list)
        total_success += s_cnt
        total_failed += f_cnt
        for item in success_list[:5]:
            sample_addresses.extend(extract_addresses_from_json(item))
        print(f'📊 本秒完成 成功 {s_cnt} / 失败 {f_cnt}，耗时 {dt:.2f}s')
        per_sec.append({"sec_index": sec + 1, "success": s_cnt, "failed": f_cnt, "elapsed_sec": round(dt, 3)})
        if dt < 1.0:
            time.sleep(1.0 - dt)

    # 去重样本
    seen = set()
    sample_addresses = [a for a in sample_addresses if not (a in seen or seen.add(a))]

    return {
        "mode": "fixed",
        "qps": qps,
        "duration_sec": duration_sec,
        "total_success": total_success,
        "total_failed": total_failed,
        "per_sec": per_sec,
        "sample_addresses": sample_addresses[:20],  # 返回最多 20 个样本
    }


def run_address_stress_staircase(start_concurrency: int,
                                 end_concurrency: int,
                                 step_duration_sec: int,
                                 lock_time: Optional[int] = None,
                                 chain_name: Optional[str] = None,
                                 wallet_id: Optional[int] = None) -> Dict[str, Any]:
    """阶梯并发的地址获取压测：从 start_concurrency 到 end_concurrency，每阶段持续 step_duration_sec 秒。

    每个阶段的每一秒，会以并发度=当前阶段并发，发送同等数量的请求，并在不足 1s 时补齐等待。
    返回逐阶段/逐秒统计、总成功/失败以及样本地址。
    """
    if start_concurrency <= 0 or end_concurrency <= 0 or step_duration_sec <= 0:
        raise ValueError('start_concurrency、end_concurrency、step_duration_sec 必须为正整数')

    conc_list = list(range(start_concurrency, end_concurrency + 1)) if end_concurrency >= start_concurrency else list(range(start_concurrency, end_concurrency - 1, -1))

    total_success = 0
    total_failed = 0
    per_stage: List[Dict[str, Any]] = []
    sample_addresses: List[str] = []

    for conc in conc_list:
        print(f'\n🚩 阶段开始：目标并发 {conc}')
        stage_rec = {"concurrency": conc, "seconds": []}
        os.environ['GETADDR_MAX_WORKERS'] = str(conc)
        for sec in range(step_duration_sec):
            print(f'⏱️ 阶段 {conc} 并发 - 第 {sec+1}/{step_duration_sec} 秒')
            t0 = time.time()
            success_list, fail_list = batch_get_recharge_address_json(
                total=conc,
                lock_time=str(lock_time) if lock_time is not None else None,
                chain_name=chain_name,
                wallet_id=str(wallet_id) if wallet_id is not None else None,
            )
            dt = time.time() - t0
            s_cnt = len(success_list)
            f_cnt = len(fail_list)
            total_success += s_cnt
            total_failed += f_cnt
            for item in success_list[:5]:
                sample_addresses.extend(extract_addresses_from_json(item))
            print(f'📊 本秒完成 成功 {s_cnt} / 失败 {f_cnt}，耗时 {dt:.2f}s')
            stage_rec["seconds"].append({"sec_index": sec + 1, "success": s_cnt, "failed": f_cnt, "elapsed_sec": round(dt, 3)})
            if dt < 1.0:
                time.sleep(1.0 - dt)
        per_stage.append(stage_rec)

    # 去重样本
    seen = set()
    sample_addresses = [a for a in sample_addresses if not (a in seen or seen.add(a))]

    return {
        "mode": "staircase",
        "start_concurrency": start_concurrency,
        "end_concurrency": end_concurrency,
        "step_duration_sec": step_duration_sec,
        "total_success": total_success,
        "total_failed": total_failed,
        "per_stage": per_stage,
        "sample_addresses": sample_addresses[:20],
    }