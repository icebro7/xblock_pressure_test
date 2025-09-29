import os
import sys
import json
from typing import Dict, Optional
import requests
import time

# 确保从子目录运行时也能导入到项目根下的 common.getToken
try:
    from common.getToken import get_token_with_auto_refresh
except ModuleNotFoundError:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    from common.getToken import get_token_with_auto_refresh

# 与其他模块保持一致的通用头部（尽量贴近浏览器/你之前提供的 curl）
BASE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0',
    'Accept': 'application/json, text/plain, */*',
    'sec-ch-ua-platform': '"Windows"',
    'sec-ch-ua': '"Not;A=Brand";v="99", "Microsoft Edge";v="139", "Chromium";v="139"',
    'sec-ch-ua-mobile': '?0',
    'origin': 'https://xblock-test.charprotocol.com',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-mode': 'cors',
    'sec-fetch-dest': 'empty',
    'referer': 'https://xblock-test.charprotocol.com/admin/',
    'accept-language': 'en,zh-CN;q=0.9,zh;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'priority': 'u=1, i',
    # Content-Type 这里也显式声明（requests 使用 json= 也会加），确保与后端预期一致
    'Content-Type': 'application/json',
}

SEND_URL = 'https://xblock-test.charprotocol.com/api/asset/member/wallet/send/tx'

# 探测 SOCKS 支持
try:
    import socks  # type: ignore
    HAS_SOCKS = True
except Exception:
    HAS_SOCKS = False


def normalize_url(u: Optional[str]) -> Optional[str]:
    if not u:
        return u
    u = u.strip()
    if not u:
        return None
    if not (u.startswith('http://') or u.startswith('https://') or u.startswith('socks5://') or u.startswith('socks5h://')):
        u = 'http://' + u
    return u


def normalize_proxies(p: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in p.items():
        if isinstance(v, str):
            nv = normalize_url(v)
            if nv:
                out[k] = nv
    return out


def build_proxy_candidates() -> list[Dict[str, str]]:
    candidates: list[Dict[str, str]] = []

    http_env = normalize_url(os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy'))
    https_env = normalize_url(os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy'))
    all_env = normalize_url(os.environ.get('ALL_PROXY') or os.environ.get('all_proxy'))
    if any([http_env, https_env, all_env]):
        proxies_env: Dict[str, str] = {}
        if all_env:
            proxies_env = {'http': all_env, 'https': all_env}
        else:
            if http_env:
                proxies_env['http'] = http_env
            if https_env:
                proxies_env['https'] = https_env
        if proxies_env:
            candidates.append(proxies_env)

    # 本地常见代理端口（如 Clash）
    candidates.append({'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'})

    # SOCKS5h（若可用）
    if HAS_SOCKS:
        candidates.append({'http': 'socks5h://127.0.0.1:7891', 'https': 'socks5h://127.0.0.1:7891'})

    return candidates


def get_verify_option() -> object:
    """决定 requests 的 verify 参数：
    优先使用可用证书文件（REQUESTS_CA_BUNDLE/SSL_CERT_FILE/CURL_CA_BUNDLE/PROXY_CA_BUNDLE），
    若设置 DISABLE_TLS_VERIFY=1 则关闭校验（仅调试用）。
    默认 True。
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
            return p
    if os.getenv('DISABLE_TLS_VERIFY') == '1':
        try:
            import urllib3  # type: ignore
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        return False
    return True


def get_token_for_auth() -> str:
    # 允许通过环境变量 TOKEN_REFRESH_INTERVAL_SEC 控制刷新间隔（秒），默认 300
    interval_env = os.getenv('TOKEN_REFRESH_INTERVAL_SEC')
    try:
        interval = int(interval_env) if interval_env is not None else None
    except Exception:
        interval = None

    token = get_token_with_auto_refresh(interval)
    if not token:
        raise RuntimeError('get_token_with_auto_refresh() 返回空 token')
    return token


def send_withdraw_tx(session: requests.Session, proxies: Dict[str, str], verify_opt: object, token: str, payload: Dict) -> requests.Response:
    """调用发送提币交易接口。

    Args:
        session: 复用的 requests 会话
        proxies: 代理配置 dict({"http":..., "https":...})
        verify_opt: TLS 校验选项（True | False | CA 文件路径字符串）
        token: Bearer token（自动小写 bearer）
        payload: POST 的 JSON 负载
    """
    headers = dict(BASE_HEADERS)
    # 注意：按你之前要求使用小写 header 名和小写 scheme
    headers['authorization'] = f'bearer {token}'

    jsessionid = os.getenv('JSESSIONID')
    if jsessionid:
        headers['Cookie'] = f'JSESSIONID={jsessionid}'

    timeout_s = float(os.getenv('SENDTX_TIMEOUT', '30'))

    resp = session.post(
        SEND_URL,
        headers=headers,
        json=payload,
        proxies=normalize_proxies(proxies),
        timeout=timeout_s,
        allow_redirects=True,
        verify=verify_opt,
    )
    return resp


def send_tx_json(payload: Dict) -> dict:
    """以与项目统一的代理/证书/认证机制调用发送交易接口，返回 JSON，失败抛异常。"""
    # 读取 key.env（如果存在）
    try:
        from dotenv import load_dotenv  # type: ignore
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_path = os.path.join(base_dir, 'key.env')
        if os.path.exists(env_path):
            load_dotenv(env_path)
        elif os.path.exists('key.env'):
            load_dotenv('key.env')
    except Exception:
        pass

    token = get_token_for_auth()
    session = requests.Session()
    verify_opt = get_verify_option()
    proxies_list = build_proxy_candidates()

    last_error: Optional[Exception] = None
    for proxies in proxies_list:
        try:
            resp = send_withdraw_tx(session, proxies, verify_opt, token, payload)
            if resp.ok:
                return resp.json()
            else:
                # 401 等直接透出内容帮助定位
                _ = resp.text[:800]
        except Exception as e:
            last_error = e
            continue

    if last_error:
        raise last_error
    raise RuntimeError('发送提币交易失败：所有代理候选均尝试失败')


# 新增：并发批量发送与压测模式
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, List, Tuple


def _extract_asset_send_id(resp: dict):
    try:
        d = resp.get('data')
        if isinstance(d, dict) and 'assetSendId' in d:
            return d.get('assetSendId')
    except Exception:
        pass
    return None


def batch_send_withdraw_json(total: int, payload: Dict, max_workers: Optional[int] = None) -> Tuple[List[dict], List[dict]]:
    """并发批量调用提币发送接口。

    Args:
        total: 本轮请求总数
        payload: 提币参数（每次相同，或可在调用层改变）
        max_workers: 线程池并发度；默认等于 total，或读取 WD_MAX_WORKERS 环境变量

    Returns:
        (success_list, fail_list)
    """
    if total <= 0:
        return [], []

    if max_workers is None:
        try:
            max_workers_env = int(os.getenv('WD_MAX_WORKERS', str(total)))
        except Exception:
            max_workers_env = total
        max_workers = max(1, min(max_workers_env, total))

    success_list: List[dict] = []
    fail_list: List[dict] = []

    def worker(idx: int) -> Tuple[bool, dict]:
        try:
            data = send_tx_json(payload)
            return True, data
        except Exception as e:
            return False, {"error": str(e)}

    # 日志文件路径：项目根/log/send_txlog.json
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(project_root, 'log')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'send_txlog.json')

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker, i) for i in range(total)]
        # 逐条消费结果，打印 assetSendId，并把完整返回追加写入日志（每行一条 JSON）
        with open(log_path, 'a', encoding='utf-8') as fh:
            for fut in as_completed(futures):
                ok, data = fut.result()
                try:
                    fh.write(json.dumps(data, ensure_ascii=False) + '\n')
                    fh.flush()
                except Exception:
                    pass

                if ok:
                    asset_id = _extract_asset_send_id(data)
                    if asset_id is not None:
                        print(f'✅ 成功提币 assetSendId: {asset_id}')
                    else:
                        print('✅ assetSendId: -')
                    success_list.append(data)
                else:
                    fail_list.append(data)

    return success_list, fail_list


def run_withdraw_stress_fixed(qps: int, duration_sec: int, payload: Dict) -> Dict[str, Any]:
    """固定并发(近似固定QPS)的提币发送压测，按秒循环执行。"""
    if qps <= 0 or duration_sec <= 0:
        raise ValueError('qps 和 duration_sec 必须为正整数')

    total_success = 0
    total_failed = 0
    per_sec: List[Dict[str, Any]] = []  # type: ignore[name-defined]
    sample_results: List[dict] = []

    for sec in range(duration_sec):
        print(f'\n⏱️ 第 {sec+1}/{duration_sec} 秒 - 目标并发 {qps}')
        t0 = time.time()
        success_list, fail_list = batch_send_withdraw_json(total=qps, payload=payload, max_workers=qps)
        dt = time.time() - t0
        s_cnt = len(success_list)
        f_cnt = len(fail_list)
        total_success += s_cnt
        total_failed += f_cnt
        sample_results.extend(success_list[:3])
        print(f'📊 本秒完成 成功 {s_cnt} / 失败 {f_cnt}，耗时 {dt:.2f}s')
        per_sec.append({"sec_index": sec + 1, "success": s_cnt, "failed": f_cnt, "elapsed_sec": round(dt, 3)})
        if dt < 1.0:
            time.sleep(1.0 - dt)

    return {
        "mode": "fixed",
        "qps": qps,
        "duration_sec": duration_sec,
        "total_success": total_success,
        "total_failed": total_failed,
        "per_sec": per_sec,
        "sample_results": sample_results[:10],
    }


def run_withdraw_stress_staircase(start_concurrency: int, end_concurrency: int, step_duration_sec: int, payload: Dict) -> Dict[str, Any]:
    """阶梯并发的提币发送压测：从 start_concurrency 到 end_concurrency，每阶段持续 step_duration_sec 秒。"""
    if start_concurrency <= 0 or end_concurrency <= 0 or step_duration_sec <= 0:
        raise ValueError('start_concurrency、end_concurrency、step_duration_sec 必须为正整数')

    conc_list = list(range(start_concurrency, end_concurrency + 1)) if end_concurrency >= start_concurrency else list(range(start_concurrency, end_concurrency - 1, -1))

    total_success = 0
    total_failed = 0
    per_stage: List[Dict[str, Any]] = []  # type: ignore[name-defined]
    sample_results: List[dict] = []

    for conc in conc_list:
        print(f'\n🚩 阶段开始：目标并发 {conc}')
        stage_rec = {"concurrency": conc, "seconds": []}
        for sec in range(step_duration_sec):
            print(f'⏱️ 阶段 {conc} 并发 - 第 {sec+1}/{step_duration_sec} 秒')
            t0 = time.time()
            success_list, fail_list = batch_send_withdraw_json(total=conc, payload=payload, max_workers=conc)
            dt = time.time() - t0
            s_cnt = len(success_list)
            f_cnt = len(fail_list)
            total_success += s_cnt
            total_failed += f_cnt
            sample_results.extend(success_list[:2])
            print(f'📊 本秒完成 成功 {s_cnt} / 失败 {f_cnt}，耗时 {dt:.2f}s')
            stage_rec["seconds"].append({"sec_index": sec + 1, "success": s_cnt, "failed": f_cnt, "elapsed_sec": round(dt, 3)})
            if dt < 1.0:
                time.sleep(1.0 - dt)
        per_stage.append(stage_rec)

    return {
        "mode": "staircase",
        "start_concurrency": start_concurrency,
        "end_concurrency": end_concurrency,
        "step_duration_sec": step_duration_sec,
        "total_success": total_success,
        "total_failed": total_failed,
        "per_stage": per_stage,
        "sample_results": sample_results[:20],
    }


def main():
    # 读取 key.env（参数与证书、代理设置）
    try:
        from dotenv import load_dotenv  # type: ignore
        if os.path.exists('key.env'):
            load_dotenv('key.env')
    except Exception:
        pass

    # 从环境变量读取参数，便于命令行快速测试
    wallet_id = os.getenv('WD_WALLET_ID')
    chain_name = os.getenv('WD_CHAIN_NAME')
    from_addr = os.getenv('WD_FROM_ADDRESS')
    to_addr = os.getenv('WD_TO_ADDRESS')
    token_addr = os.getenv('WD_TOKEN_ADDRESS', '')
    amount_env = os.getenv('WD_AMOUNT')

    payload: Dict = {}
    if wallet_id is not None:
        try:
            payload['walletId'] = int(wallet_id)
        except Exception:
            payload['walletId'] = wallet_id
    if chain_name is not None:
        payload['chainName'] = chain_name
    if from_addr is not None:
        payload['fromAddress'] = from_addr
    if to_addr is not None:
        payload['toAddress'] = to_addr
    if token_addr is not None:
        payload['tokenAddress'] = token_addr
    if amount_env is not None:
        try:
            payload['amount'] = int(amount_env)
        except Exception:
            try:
                payload['amount'] = float(amount_env)
            except Exception:
                payload['amount'] = amount_env

    # 若没有通过环境提供 payload，则示例打印并退出，避免误发
    if not payload:
        print('[INFO] 未提供 WD_* 环境变量，示例 payload：')
        example = {
            "walletId": 118,
            "chainName": "BTT_TEST",
            "fromAddress": "0x...",
            "toAddress": "0x...",
            "tokenAddress": "",
            "amount": 7000000000000000000,
        }
        print(json.dumps(example, ensure_ascii=False, indent=2))
        print('请设置 WD_WALLET_ID/WD_CHAIN_NAME/WD_FROM_ADDRESS/WD_TO_ADDRESS/WD_TOKEN_ADDRESS/WD_AMOUNT 后重试。')
        return

    # 执行发送
    try:
        token = get_token_for_auth()
        print('[INFO] 已获取 token（前 30 字符预览）:', token[:30] + '...')
        session = requests.Session()
        verify_opt = get_verify_option()
        proxies_list = build_proxy_candidates()
        last_error = None
        for idx, proxies in enumerate(proxies_list, start=1):
            try:
                print(f"[INFO] 尝试使用代理 #{idx}: {proxies}")
                resp = send_withdraw_tx(session, proxies, verify_opt, token, payload)
                content_type = resp.headers.get('Content-Type', '')
                print(f"[INFO] HTTP {resp.status_code}, Content-Type: {content_type}")
                if resp.ok:
                    try:
                        data = resp.json()
                    except Exception:
                        print('[ERROR] 响应不是 JSON：\n' + resp.text[:500])
                        continue
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                    return
                else:
                    print('[WARN] 请求失败：', resp.text[:800])
            except Exception as e:
                last_error = e
                print(f"[ERROR] 代理 {proxies} 访问失败：{e}")
                continue
        print('\n[FAIL] 所有代理候选均尝试失败。')
        if last_error:
            print(f"最后错误: {repr(last_error)}")
    except Exception as e:
        print(f"[FATAL] 执行失败: {e}")


if __name__ == '__main__':
    main()