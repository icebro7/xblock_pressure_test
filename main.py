import os
import sys
import time
import json
from typing import List, Dict, Any

# 保证项目根目录可被导入
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 引入独立的压测模块
from recharge.recharge_stress import (
    run_recharge_stress_fixed,
    run_recharge_stress_staircase,
)  # type: ignore
from recharge.address_stress import (
    run_address_stress,
    run_address_stress_fixed,
    run_address_stress_staircase,
)  # type: ignore

# 新增：导入提币发送接口
from withdrawal.sendTx import send_tx_json  # type: ignore


def do_recharge_stress():
    amount_btt = float(os.getenv('RECHARGE_AMOUNT_BTT', '0.007'))

    print('请选择压测模式:')
    print('1) 固定TPS + 持续秒数')
    print('2) 阶梯TPS（从起始TPS到结束TPS，每阶段持续若干秒）')
    mode = input('输入 1 或 2（默认 2）: ').strip() or '2'

    if mode == '1':
        default_tps = int(os.getenv('RECHARGE_TPS', '1'))
        default_duration = int(os.getenv('RECHARGE_DURATION', '10'))
        try:
            inp_tps = input(f'请输入每秒请求数 TPS（默认 {default_tps}）: ').strip()
            desired_tps = int(inp_tps) if inp_tps else default_tps
            if desired_tps <= 0:
                raise ValueError
        except Exception:
            print(f'[WARN] TPS 输入不合法，使用默认 {default_tps}')
            desired_tps = default_tps
        try:
            inp_dur = input(f'请输入持续秒数（默认 {default_duration}）: ').strip()
            duration_sec = int(inp_dur) if inp_dur else default_duration
            if duration_sec <= 0:
                raise ValueError
        except Exception:
            print(f'[WARN] 持续秒数输入不合法，使用默认 {default_duration}')
            duration_sec = default_duration

        # 可选参数：透传给地址解析（用于确定目标地址）
        lock_time = os.getenv('ADDR_LOCK_TIME')
        chain_name = os.getenv('ADDR_CHAIN_NAME', 'BTT_TEST')
        wallet_id = os.getenv('ADDR_WALLET_ID')

        result = run_recharge_stress_fixed(
            tps=desired_tps,
            duration_sec=duration_sec,
            amount_btt=amount_btt,
            lock_time=int(lock_time) if lock_time else None,
            chain_name=chain_name,
            wallet_id=int(wallet_id) if wallet_id else None,
        )
        print('\n📊 充值压测结果（固定模式）:')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        default_start_tps = int(os.getenv('RECHARGE_START_TPS', '1'))
        default_end_tps = int(os.getenv('RECHARGE_END_TPS', '5'))
        default_step_duration = int(os.getenv('RECHARGE_STEP_DURATION', '5'))
        try:
            inp_start = input(f'请输入起始 TPS（默认 {default_start_tps}）: ').strip()
            start_tps = int(inp_start) if inp_start else default_start_tps
            if start_tps <= 0:
                raise ValueError
        except Exception:
            print(f'[WARN] 起始 TPS 输入不合法，使用默认 {default_start_tps}')
            start_tps = default_start_tps
        try:
            inp_end = input(f'请输入结束 TPS（默认 {default_end_tps}）: ').strip()
            end_tps = int(inp_end) if inp_end else default_end_tps
            if end_tps <= 0:
                raise ValueError
        except Exception:
            print(f'[WARN] 结束 TPS 输入不合法，使用默认 {default_end_tps}')
            end_tps = default_end_tps
        try:
            inp_step = input(f'请输入每阶段持续秒数（默认 {default_step_duration}）: ').strip()
            step_duration = int(inp_step) if inp_step else default_step_duration
            if step_duration <= 0:
                raise ValueError
        except Exception:
            print(f'[WARN] 每阶段持续秒数输入不合法，使用默认 {default_step_duration}')
            step_duration = default_step_duration

        # 可选参数：透传给地址解析（用于确定目标地址）
        lock_time = os.getenv('ADDR_LOCK_TIME')
        chain_name = os.getenv('ADDR_CHAIN_NAME', 'BTT_TEST')
        wallet_id = os.getenv('ADDR_WALLET_ID')

        result = run_recharge_stress_staircase(
            start_tps=start_tps,
            end_tps=end_tps,
            step_duration_sec=step_duration,
            amount_btt=amount_btt,
            lock_time=int(lock_time) if lock_time else None,
            chain_name=chain_name,
            wallet_id=int(wallet_id) if wallet_id else None,
        )
        print('\n📊 充值压测结果（阶梯模式）:')
        print(json.dumps(result, ensure_ascii=False, indent=2))


def do_address_stress():
    print('📮 地址获取压测（独立）')
    print('请选择压测模式:')
    print('1) 固定并发 + 持续秒数')
    print('2) 阶梯并发（从起始并发到结束并发，每阶段持续若干秒）')
    mode = input('输入 1 或 2（默认 2）: ').strip() or '2'

    # 可选参数（透传给地址接口）
    lock_time = os.getenv('ADDR_LOCK_TIME')
    chain_name = os.getenv('ADDR_CHAIN_NAME', 'BTT_TEST')
    wallet_id = os.getenv('ADDR_WALLET_ID')

    if mode == '1':
        default_qps = int(os.getenv('ADDR_QPS', '10'))
        default_duration = int(os.getenv('ADDR_DURATION', '10'))
        try:
            inp_qps = input(f'请输入并发/QPS（默认 {default_qps}）: ').strip()
            qps = int(inp_qps) if inp_qps else default_qps
            if qps <= 0:
                raise ValueError
        except Exception:
            print(f'[WARN] QPS 输入不合法，使用默认 {default_qps}')
            qps = default_qps
        try:
            inp_dur = input(f'请输入持续秒数（默认 {default_duration}）: ').strip()
            duration_sec = int(inp_dur) if inp_dur else default_duration
            if duration_sec <= 0:
                raise ValueError
        except Exception:
            print(f'[WARN] 持续秒数输入不合法，使用默认 {default_duration}')
            duration_sec = default_duration

        result = run_address_stress_fixed(
            qps=qps,
            duration_sec=duration_sec,
            lock_time=int(lock_time) if lock_time else None,
            chain_name=chain_name,
            wallet_id=int(wallet_id) if wallet_id else None,
        )
        print('\n📊 地址获取压测结果（固定模式）:')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        default_start = int(os.getenv('ADDR_START_CONCURRENCY', '1'))
        default_end = int(os.getenv('ADDR_END_CONCURRENCY', '10'))
        default_step_duration = int(os.getenv('ADDR_STEP_DURATION', '5'))
        try:
            inp_start = input(f'请输入起始并发（默认 {default_start}）: ').strip()
            start_conc = int(inp_start) if inp_start else default_start
            if start_conc <= 0:
                raise ValueError
        except Exception:
            print(f'[WARN] 起始并发输入不合法，使用默认 {default_start}')
            start_conc = default_start
        try:
            inp_end = input(f'请输入结束并发（默认 {default_end}）: ').strip()
            end_conc = int(inp_end) if inp_end else default_end
            if end_conc <= 0:
                raise ValueError
        except Exception:
            print(f'[WARN] 结束并发输入不合法，使用默认 {default_end}')
            end_conc = default_end
        try:
            inp_step = input(f'请输入每阶段持续秒数（默认 {default_step_duration}）: ').strip()
            step_duration = int(inp_step) if inp_step else default_step_duration
            if step_duration <= 0:
                raise ValueError
        except Exception:
            print(f'[WARN] 每阶段持续秒数输入不合法，使用默认 {default_step_duration}')
            step_duration = default_step_duration

        result = run_address_stress_staircase(
            start_concurrency=start_conc,
            end_concurrency=end_conc,
            step_duration_sec=step_duration,
            lock_time=int(lock_time) if lock_time else None,
            chain_name=chain_name,
            wallet_id=int(wallet_id) if wallet_id else None,
        )
        print('\n📊 地址获取压测结果（阶梯模式）:')
        print(json.dumps(result, ensure_ascii=False, indent=2))


# 新增：提币单次发送流程（从控制台输入参数）
def do_withdrawal_flow():
    print('💸 提币发送压测')
    # 读取默认值（来自环境变量，便于脚本化）
    def_env = {
        'wallet_id': os.getenv('WD_WALLET_ID', '118'),
        'chain_name': os.getenv('WD_CHAIN_NAME', 'BTT_TEST'),
        'from_address': os.getenv('WD_FROM_ADDRESS', ''),
        'to_address': os.getenv('WD_TO_ADDRESS', ''),
        'token_address': os.getenv('WD_TOKEN_ADDRESS', ''),
        'amount': os.getenv('WD_AMOUNT', '7'),
    }

    try:
        inp_wallet = input(f"walletId（默认 {def_env['wallet_id']}）: ").strip() or def_env['wallet_id']
        try:
            wallet_id = int(inp_wallet)
        except Exception:
            wallet_id = inp_wallet

        chain_name = input(f"chainName（默认 {def_env['chain_name']}）: ").strip() or def_env['chain_name']
        from_addr = input(f"fromAddress（默认 {def_env['from_address']}）: ").strip() or def_env['from_address']
        to_addr = input(f"toAddress（默认 {def_env['to_address']}）: ").strip() or def_env['to_address']
        token_addr = input(f"tokenAddress（默认 {def_env['token_address']}，可留空）: ").strip() or def_env['token_address']
        inp_amount = input(f"amount（默认 {def_env['amount']}）: ").strip() or def_env['amount']

        if not from_addr or not to_addr or not inp_amount:
            print('[ERROR] 必填项缺失：fromAddress/toAddress/amount 不能为空。')
            return

        # 尝试解析 amount 为 int/float
        amount_val: Any
        try:
            amount_val = int(inp_amount)
        except Exception:
            try:
                amount_val = float(inp_amount)
            except Exception:
                amount_val = inp_amount

        payload = {
            'walletId': wallet_id,
            'chainName': chain_name,
            'fromAddress': from_addr,
            'toAddress': to_addr,
            'tokenAddress': token_addr,
            'amount': amount_val,
        }

        print('[INFO] 参数如下（将用于压测每次请求）:')
        print(json.dumps(payload, ensure_ascii=False, indent=2))

        # 选择压测模式（不再需要“是否发送”的确认）
        print('请选择提币压测模式:')
        print('1) 固定并发 + 持续秒数')
        print('2) 阶梯并发（从起始并发到结束并发，每阶段持续若干秒）')
        mode = input('输入 1 或 2（默认 2）: ').strip() or '2'

        if mode == '1':
            default_qps = int(os.getenv('WD_QPS', '10'))
            default_duration = int(os.getenv('WD_DURATION', '10'))
            try:
                inp_qps = input(f'请输入并发/QPS（默认 {default_qps}）: ').strip()
                qps = int(inp_qps) if inp_qps else default_qps
                if qps <= 0:
                    raise ValueError
            except Exception:
                print(f'[WARN] QPS 输入不合法，使用默认 {default_qps}')
                qps = default_qps
            try:
                inp_dur = input(f'请输入持续秒数（默认 {default_duration}）: ').strip()
                duration_sec = int(inp_dur) if inp_dur else default_duration
                if duration_sec <= 0:
                    raise ValueError
            except Exception:
                print(f'[WARN] 持续秒数输入不合法，使用默认 {default_duration}')
                duration_sec = default_duration

            # 延迟导入，避免循环依赖
            from withdrawal.sendTx import run_withdraw_stress_fixed  # type: ignore
            result = run_withdraw_stress_fixed(qps=qps, duration_sec=duration_sec, payload=payload)
            print('\n📊 提币压测结果（固定模式）:')
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            default_start = int(os.getenv('WD_START_CONCURRENCY', '1'))
            default_end = int(os.getenv('WD_END_CONCURRENCY', '10'))
            default_step_duration = int(os.getenv('WD_STEP_DURATION', '5'))
            try:
                inp_start = input(f'请输入起始并发（默认 {default_start}）: ').strip()
                start_conc = int(inp_start) if inp_start else default_start
                if start_conc <= 0:
                    raise ValueError
            except Exception:
                print(f'[WARN] 起始并发输入不合法，使用默认 {default_start}')
                start_conc = default_start
            try:
                inp_end = input(f'请输入结束并发（默认 {default_end}）: ').strip()
                end_conc = int(inp_end) if inp_end else default_end
                if end_conc <= 0:
                    raise ValueError
            except Exception:
                print(f'[WARN] 结束并发输入不合法，使用默认 {default_end}')
                end_conc = default_end
            try:
                inp_step = input(f'请输入每阶段持续秒数（默认 {default_step_duration}）: ').strip()
                step_duration = int(inp_step) if inp_step else default_step_duration
                if step_duration <= 0:
                    raise ValueError
            except Exception:
                print(f'[WARN] 每阶段持续秒数输入不合法，使用默认 {default_step_duration}')
                step_duration = default_step_duration

            from withdrawal.sendTx import run_withdraw_stress_staircase  # type: ignore
            result = run_withdraw_stress_staircase(
                start_concurrency=start_conc,
                end_concurrency=end_conc,
                step_duration_sec=step_duration,
                payload=payload,
            )
            print('\n📊 提币压测结果（阶梯模式）:')
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f'[ERROR] 提币压测执行失败: {e}')

        result = send_tx_json(payload)
        print('\n✅ 提币接口返回:')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f'[ERROR] 提币发送失败: {e}')


def main():
    print('请选择要执行的操作:')
    print('1) 充值完整流程压测')
    print('2) 提币完整流程压测')
    print('3) 地址获取接口压测（独立）')
    print('0) 退出')
    choice = input('输入序号后回车: ').strip()

    if choice == '1':
        do_recharge_stress()
    elif choice == '2':
        # 集成提币发送流程
        do_withdrawal_flow()
    elif choice == '3':
        do_address_stress()
    else:
        print('已退出。')


if __name__ == '__main__':
    main()
