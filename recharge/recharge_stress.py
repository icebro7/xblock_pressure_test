import os
import sys
import time
import json
from typing import Any, Dict, List, Optional

# 允许从项目根导入
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from recharge.sendTx import batch_transfer_btt  # type: ignore
from recharge.getAddress import get_recharge_address_json  # type: ignore
from recharge.address_stress import extract_addresses_from_json  # type: ignore

LOG_DIR = os.path.join(PROJECT_ROOT, 'log')
LOG_PATH = os.path.join(LOG_DIR, 'transfer_log.json')


def ensure_log_file():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump({"successful": [], "failed": []}, f, ensure_ascii=False, indent=2)


def append_transfer_log(successful: List[Dict[str, Any]], failed: List[Dict[str, Any]]):
    ensure_log_file()
    try:
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {"successful": [], "failed": []}
    data.setdefault('successful', [])
    data.setdefault('failed', [])
    data['successful'].extend(successful)
    data['failed'].extend(failed)
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _resolve_target_address(lock_time: Optional[int] = None,
                            chain_name: Optional[str] = None,
                            wallet_id: Optional[int] = None) -> Optional[str]:
    """解析目标充值地址。优先从接口获取，否则使用环境变量 RECHARGE_TARGET_ADDRESS。"""
    try:
        resp = get_recharge_address_json(lock_time=lock_time, chain_name=chain_name, wallet_id=wallet_id)
        addrs = extract_addresses_from_json(resp)
        if addrs:
            return addrs[0]
    except Exception as e:
        print(f'[WARN] 获取充值地址失败，尝试使用环境变量 RECHARGE_TARGET_ADDRESS: {e}')
    fallback = os.getenv('RECHARGE_TARGET_ADDRESS')
    return fallback.strip() if fallback else None


def run_recharge_stress_fixed(tps: int,
                              duration_sec: int,
                              amount_btt: Optional[float] = None,
                              lock_time: Optional[int] = None,
                              chain_name: Optional[str] = None,
                              wallet_id: Optional[int] = None) -> Dict[str, Any]:
    """固定 TPS 充值压测。返回结构化统计结果。"""
    if tps <= 0 or duration_sec <= 0:
        raise ValueError('tps 和 duration_sec 必须为正整数')

    amt = amount_btt if amount_btt is not None else float(os.getenv('RECHARGE_AMOUNT_BTT', '0.007'))
    target = _resolve_target_address(lock_time=lock_time, chain_name=chain_name, wallet_id=wallet_id)
    if not target:
        raise RuntimeError('无法解析到充值地址，请检查接口或设置 RECHARGE_TARGET_ADDRESS')

    print(f'🚀 固定速率压测开始：TPS={tps}，持续 {duration_sec} 秒，每笔 {amt} BTT')
    print(f'🎯 目标充值地址: {target}')

    current_nonce = None
    total_success = 0
    total_failed = 0
    per_sec: List[Dict[str, Any]] = []

    ensure_log_file()
    for sec in range(duration_sec):
        print(f'\n⏱️ 第 {sec+1}/{duration_sec} 秒 - 目标 {tps} tx/s')
        recipients = [target] * tps
        t0 = time.time()
        successful, failed, current_nonce = batch_transfer_btt(recipients, amt, start_nonce=current_nonce)
        append_transfer_log(successful, failed)
        dt = time.time() - t0
        s_cnt = len(successful)
        f_cnt = len(failed)
        total_success += s_cnt
        total_failed += f_cnt
        print(f'📊 本秒完成 成功 {s_cnt} / 失败 {f_cnt}，耗时 {dt:.2f}s  日志: {LOG_PATH}')
        per_sec.append({"sec_index": sec + 1, "success": s_cnt, "failed": f_cnt, "elapsed_sec": round(dt, 3)})
        if dt < 1.0:
            time.sleep(1.0 - dt)

    print('\n✅ 固定速率压测完成。记录已写入 log/transfer_log.json')
    return {
        "mode": "fixed",
        "tps": tps,
        "duration_sec": duration_sec,
        "amount_btt": amt,
        "total_success": total_success,
        "total_failed": total_failed,
        "per_sec": per_sec,
        "log_path": LOG_PATH,
    }


def run_recharge_stress_staircase(start_tps: int,
                                  end_tps: int,
                                  step_duration_sec: int,
                                  amount_btt: Optional[float] = None,
                                  lock_time: Optional[int] = None,
                                  chain_name: Optional[str] = None,
                                  wallet_id: Optional[int] = None) -> Dict[str, Any]:
    """阶梯 TPS 充值压测。返回结构化统计结果。"""
    if start_tps <= 0 or end_tps <= 0 or step_duration_sec <= 0:
        raise ValueError('start_tps、end_tps、step_duration_sec 必须为正整数')

    amt = amount_btt if amount_btt is not None else float(os.getenv('RECHARGE_AMOUNT_BTT', '0.007'))
    target = _resolve_target_address(lock_time=lock_time, chain_name=chain_name, wallet_id=wallet_id)
    if not target:
        raise RuntimeError('无法解析到充值地址，请检查接口或设置 RECHARGE_TARGET_ADDRESS')

    print(f'🚀 阶梯速率压测开始：从 {start_tps} TPS 到 {end_tps} TPS，每阶段 {step_duration_sec} 秒，每笔 {amt} BTT')
    print(f'🎯 目标充值地址: {target}')

    tps_list = list(range(start_tps, end_tps + 1)) if end_tps >= start_tps else list(range(start_tps, end_tps - 1, -1))
    current_nonce = None
    total_success = 0
    total_failed = 0
    per_stage: List[Dict[str, Any]] = []

    ensure_log_file()
    for tps in tps_list:
        print(f'\n🚩 阶段开始：目标 {tps} tx/s')
        stage_rec = {"tps": tps, "seconds": []}  # type: ignore[dict-item]
        for sec in range(step_duration_sec):
            print(f'⏱️ 阶段 {tps} tx/s - 第 {sec+1}/{step_duration_sec} 秒')
            recipients = [target] * tps
            t0 = time.time()
            successful, failed, current_nonce = batch_transfer_btt(recipients, amt, start_nonce=current_nonce)
            append_transfer_log(successful, failed)
            dt = time.time() - t0
            s_cnt = len(successful)
            f_cnt = len(failed)
            total_success += s_cnt
            total_failed += f_cnt
            print(f'📊 本秒完成 成功 {s_cnt} / 失败 {f_cnt}，耗时 {dt:.2f}s')
            stage_rec["seconds"].append({"sec_index": sec + 1, "success": s_cnt, "failed": f_cnt, "elapsed_sec": round(dt, 3)})
            if dt < 1.0:
                time.sleep(1.0 - dt)
        per_stage.append(stage_rec)

    print('\n✅ 阶梯速率压测完成。记录已写入 log/transfer_log.json')
    return {
        "mode": "staircase",
        "start_tps": start_tps,
        "end_tps": end_tps,
        "step_duration_sec": step_duration_sec,
        "amount_btt": amt,
        "total_success": total_success,
        "total_failed": total_failed,
        "per_stage": per_stage,
        "log_path": LOG_PATH,
    }