import os
import json
from web3 import Web3
from dotenv import load_dotenv
from typing import Optional, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
import time

# 加载环境变量（显式指定 key.env）
load_dotenv('key.env')

# 配置BTT测试网
BTT_RPC_URL = os.getenv('BTT_RPC_URL')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')
SENDER_ADDRESS = '0x361cA2860F5Cf6F8498F69D0Ef4E31e39Dda4D3b'  # 替换为你的发送地址

# 先校验环境变量是否读取成功
if not BTT_RPC_URL:
    print("未在 key.env 中读取到 BTT_RPC_URL，请确认文件存在且变量名正确")
    exit(1)


def normalize_url(u: Optional[str]) -> Optional[str]:
    if not u:
        return u
    u = u.strip()
    if not u:
        return None
    # 未写 scheme 则默认为 http
    if not (u.startswith('http://') or u.startswith('https://')):
        u = 'http://' + u
    return u


def build_proxies_from_env() -> Optional[Dict[str, str]]:
    """从 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY 构造 proxies 字典；若都为空返回 None。"""
    http_env = normalize_url(os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy'))
    https_env = normalize_url(os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy'))
    all_env = normalize_url(os.environ.get('ALL_PROXY') or os.environ.get('all_proxy'))

    proxies: Dict[str, str] = {}
    if all_env:
        proxies = {'http': all_env, 'https': all_env}
    else:
        if http_env:
            proxies['http'] = http_env
        if https_env:
            proxies['https'] = https_env

    return proxies if proxies else None


def get_verify_option():
    """决定 requests 的 verify：
    - 若 PROXY_CA_BUNDLE/REQUESTS_CA_BUNDLE/SSL_CERT_FILE/CURL_CA_BUNDLE 指向存在的证书文件，则返回该路径
    - 若 DISABLE_TLS_VERIFY=1，则返回 False（仅调试用）并抑制 InsecureRequestWarning
    - 否则返回 True
    """
    custom_ca = os.getenv('PROXY_CA_BUNDLE')
    env_cas = [
        custom_ca,
        os.getenv('REQUESTS_CA_BUNDLE'),
        os.getenv('SSL_CERT_FILE'),
        os.getenv('CURL_CA_BUNDLE'),
    ]
    for p in env_cas:
        if p and os.path.isfile(p):
            print(f"[INFO] 使用证书文件进行 TLS 校验: {p}")
            return p
    if os.getenv('DISABLE_TLS_VERIFY') == '1':
        print('[WARN] 已暂时关闭 TLS 证书校验')
        try:
            import urllib3  # type: ignore
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        return False
    return True


def init_web3() -> Web3:
    verify_opt = get_verify_option()
    proxies = build_proxies_from_env()
    # 打印模式，便于定位“开代理不通”的问题
    print(f"[INFO] TLS verify 模式: {verify_opt}")
    print(f"[INFO] 使用代理: {proxies if proxies else '无'}")

    request_kwargs = {
        'timeout': 30,
        'verify': verify_opt,
    }
    # requests 支持 proxies 字段，这里通过 request_kwargs 传入
    if proxies:
        request_kwargs['proxies'] = proxies

    w3 = Web3(Web3.HTTPProvider(BTT_RPC_URL, request_kwargs=request_kwargs))

    # 调整 HTTP 连接池大小，提升高并发吞吐
    try:
        pool_size = int(os.getenv('SENDTX_POOL_MAXSIZE', '64'))
    except Exception:
        pool_size = 64
    try:
        provider = getattr(w3, 'provider', None)
        session = None
        if provider is not None:
            session = getattr(provider, 'session', None) or getattr(provider, '_session', None) or getattr(provider, '_request_session', None)
        if isinstance(session, requests.Session):
            adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=0)
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            print(f"[INFO] HTTP 连接池大小已设置为 {pool_size}")
    except Exception as e:
        print(f"[WARN] 无法设置 HTTP 连接池: {e}")

    return w3


# 初始化Web3（带代理与证书设置）
w3 = init_web3()

# 检查连接
if not w3.is_connected():
    print(f"无法连接到BTT测试网，当前RPC: {BTT_RPC_URL}")
    exit(1)

print(f"已连接到BTT测试网，当前区块: {w3.eth.block_number}")

# 新增: 检查 PRIVATE_KEY
if not PRIVATE_KEY:
    print("未在 key.env 中读取到 PRIVATE_KEY，请配置后再试")
    exit(1)

# 可选: 打印链ID并校验是否为 1029
try:
    chain_id = w3.eth.chain_id
    print(f"Chain ID: {chain_id}")
    if chain_id != 1029:
        print("警告: 当前连接的链 ID 不是 1029（BTTC Donau）")
except Exception:
    pass

# 设置发送账户
account = w3.eth.account.from_key(PRIVATE_KEY)
print(f"使用账户: {account.address}")

# 可选: 校验 SENDER_ADDRESS 一致性
if SENDER_ADDRESS and SENDER_ADDRESS.lower() != account.address.lower():
    print(f"警告: SENDER_ADDRESS 与私钥推导地址不一致。SENDER_ADDRESS={SENDER_ADDRESS}, 私钥地址={account.address}")

# 检查余额
balance = w3.eth.get_balance(account.address)
print(f"账户余额: {w3.from_wei(balance, 'ether')} BTT")

# 统一日志路径（基于项目根目录）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, 'log')
LOG_PATH = os.path.join(LOG_DIR, 'transfer_log.json')

# 生成接收地址列表 (这里示例生成5个地址，实际使用时可以替换为你自己的地址列表)
recipients = ["0x1f6642e250e7e15865c54963ce65e8635c564eae"]

# 替换原先的临时日志目录创建逻辑，改为提供统一的日志工具函数

def ensure_log_file():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump({"successful": [], "failed": []}, f, ensure_ascii=False, indent=2)


def append_transfer_log(successful, failed):
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


def batch_transfer_btt(recipients, amount_btt, start_nonce=None):
    """向多个地址发送BTT
    
    Args:
        recipients: 接收地址列表
        amount_btt: 每笔转账金额
        start_nonce: 起始nonce，如果为None则自动获取
    
    Returns:
        (successful_txs, failed_txs, next_nonce)
    """
    successful_txs: List[Dict] = []
    failed_txs: List[Dict] = []

    # 计算总数并设置并发度（默认使用 total 实现“满并发”）
    total = len(recipients)
    if total == 0:
        next_nonce = start_nonce if start_nonce is not None else w3.eth.get_transaction_count(account.address)
        return successful_txs, failed_txs, next_nonce

    max_workers_env_raw = os.getenv('SENDTX_MAX_WORKERS', '').strip()
    if max_workers_env_raw == '' or max_workers_env_raw == '0' or max_workers_env_raw.lower() == 'auto':
        max_workers = total
    else:
        try:
            max_workers = max(1, min(int(max_workers_env_raw), total))
        except Exception:
            max_workers = total
    concurrent_mode = max_workers >= 2

    # 获取当前nonce（支持外部传入以避免并发冲突）
    if start_nonce is not None:
        base_nonce = start_nonce
        print(f"[DEBUG] 使用传入 nonce: {base_nonce}")
    else:
        base_nonce = w3.eth.get_transaction_count(account.address)
        print(f"[DEBUG] 自动获取 nonce: {base_nonce}")

    # GasPrice 策略：可通过 FIXED_GAS_PRICE_GWEI 固定，否则取链上建议
    fixed_gas_gwei_env = os.getenv('FIXED_GAS_PRICE_GWEI')
    try:
        fixed_gas_price = w3.to_wei(fixed_gas_gwei_env, 'gwei') if fixed_gas_gwei_env else None
    except Exception:
        fixed_gas_price = None

    if fixed_gas_price is not None:
        gas_price_value = fixed_gas_price
    else:
        try:
            gas_price_value = w3.eth.gas_price
        except Exception:
            gas_price_value = w3.to_wei('50', 'gwei')

    # 是否进行 estimate_gas（默认关闭以提升并发速度）
    estimate_gas = os.getenv('ESTIMATE_GAS', '0') == '1'

    # 预先转换金额以减少循环内开销
    value_wei = w3.to_wei(amount_btt, 'ether')

    def build_and_send(recipient, nonce_assigned, index, total):
        try:
            # 兼容字符串或 {'address': '0x...'} 的输入格式，并做地址规范化
            to_raw = recipient.get('address') if isinstance(recipient, dict) else recipient
            if not to_raw:
                raise ValueError("空的接收地址")
            to_addr = Web3.to_checksum_address(to_raw.strip())

            # 基础交易（包含 from / nonce / chainId）
            base_tx = {
                'from': account.address,
                'to': to_addr,
                'value': value_wei,
                'nonce': nonce_assigned,
                'chainId': 1029  # BTT测试网的链ID
            }

            # Gas：默认固定 21000，除非显式开启估算
            if estimate_gas:
                try:
                    gas = w3.eth.estimate_gas(base_tx)
                except Exception:
                    gas = 21000
            else:
                gas = 21000

            tx = {**base_tx, 'gas': gas, 'gasPrice': gas_price_value}

            # 签名并发送
            signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = Web3.to_hex(tx_hash)
            print(f"✅ 成功发送 {index}/{total}: {tx_hash_hex} -> {to_addr} (gas={gas}, gasPrice={w3.from_wei(gas_price_value,'gwei')} gwei)")

            result = {
                'index': index,
                'to': to_addr,
                'tx_hash': tx_hash_hex,
                'gas': gas,
                'gas_price_gwei': float(w3.from_wei(gas_price_value, 'gwei')),
                'value_btt': float(amount_btt),
                'nonce': nonce_assigned,
                'timestamp': int(time.time()),
            }
            return ('ok', result)
        except Exception as e:
            target_disp = to_addr if isinstance(to_addr, str) else str(to_addr)
            print(f"❌ 发送失败 {index}/{total} -> {target_disp}: {e}")
            return ('err', {
                'index': index,
                'to': target_disp,
                'error': str(e)
            })

    if concurrent_mode:
        tasks = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 预分配 nonce，避免锁竞争与重复
            for i, recipient in enumerate(recipients, start=1):
                assigned_nonce = base_nonce + (i - 1)
                tasks.append(executor.submit(build_and_send, recipient, assigned_nonce, i, total))

            for fut in as_completed(tasks):
                status, payload = fut.result()
                if status == 'ok':
                    successful_txs.append(payload)
                else:
                    failed_txs.append(payload)
    else:
        # 顺序发送（兼容旧逻辑）
        nonce = base_nonce
        for i, recipient in enumerate(recipients, start=1):
            status, payload = build_and_send(recipient, nonce, i, total)
            if status == 'ok':
                successful_txs.append(payload)
            else:
                failed_txs.append(payload)
            nonce += 1

    # 发送结束后按需记录日志（默认开启，可通过 SENDTX_SELF_LOG=0 关闭，避免与 main.py 的日志重复）
    if os.getenv('SENDTX_SELF_LOG', '1') == '1':
        try:
            append_transfer_log(successful_txs, failed_txs)
            print(f"🧾 日志已记录: {LOG_PATH}")
        except Exception as e:
            print(f"[WARN] 写入交易日志失败: {e}")

    next_nonce = base_nonce + total
    return successful_txs, failed_txs, next_nonce

# 作为库模块使用：由 main.py 调用 batch_transfer_btt 进行转账与（可选）记录日志


if __name__ == '__main__':
    import argparse
    import time

    parser = argparse.ArgumentParser(description='Standalone sender for BTT recharge (batch_transfer_btt).')
    parser.add_argument('-r', '--recipient', help='目标充值地址，默认读取 RECHARGE_TARGET_ADDRESS 或内置示例地址')
    parser.add_argument('-n', '--count', type=int, default=1, help='发送笔数（同一个地址会重复提交），默认 1')
    parser.add_argument('-a', '--amount', type=float, default=None, help='每笔 BTT 金额，例如 0.007；默认读取 RECHARGE_AMOUNT_BTT 或 0.007')
    parser.add_argument('--max-workers', default=None, help='并发度，整数或 auto（默认 auto=满并发）')
    parser.add_argument('--fixed-gas-gwei', default=None, help='固定 gasPrice（单位 gwei）；不传则使用链上建议')
    parser.add_argument('--estimate-gas', action='store_true', help='开启 estimate_gas（默认关闭以提速）')
    parser.add_argument('--start-nonce', type=int, default=None, help='起始 nonce；不传则自动获取当前 nonce')

    args = parser.parse_args()

    # 环境变量设置（仅对当前进程生效）
    if args.max_workers is not None:
        os.environ['SENDTX_MAX_WORKERS'] = str(args.max_workers)
    if args.fixed_gas_gwei is not None:
        os.environ['FIXED_GAS_PRICE_GWEI'] = str(args.fixed_gas_gwei)
    if args.estimate_gas:
        os.environ['ESTIMATE_GAS'] = '1'

    # 解析目标地址与金额
    default_target = os.getenv('RECHARGE_TARGET_ADDRESS') or (recipients[0] if isinstance(recipients, list) and recipients else None)
    target = args.recipient or default_target
    if not target:
        raise SystemExit('未提供目标地址。请使用 --recipient 或设置环境变量 RECHARGE_TARGET_ADDRESS')

    amount_btt = args.amount if args.amount is not None else float(os.getenv('RECHARGE_AMOUNT_BTT', '0.007'))

    print(f'🚀 单文件调试启动：向 {target} 发送 {args.count} 笔，每笔 {amount_btt} BTT')
    if 'SENDTX_MAX_WORKERS' in os.environ:
        print(f"[INFO] 并发度: {os.environ['SENDTX_MAX_WORKERS']}")
    if 'FIXED_GAS_PRICE_GWEI' in os.environ:
        print(f"[INFO] 固定 gasPrice: {os.environ['FIXED_GAS_PRICE_GWEI']} gwei")
    print('[INFO] estimate_gas:', '开启' if os.getenv('ESTIMATE_GAS','0')=='1' else '关闭')

    batch = [target] * int(args.count)
    t0 = time.time()
    ok, err, next_nonce = batch_transfer_btt(batch, amount_btt, start_nonce=args.start_nonce)
    dt = time.time() - t0

    print(f"\n✅ 完成。成功 {len(ok)} / 失败 {len(err)}，耗时 {dt:.3f}s，next_nonce={next_nonce}")
    print(f"🧾 日志: {LOG_PATH}")