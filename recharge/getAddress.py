import os
import sys
import json
from typing import Dict, List, Optional, Tuple
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# 确保从子目录运行时也能导入到项目根下的 common.getToken
try:
    from common.getToken import get_token_with_auto_refresh
except ModuleNotFoundError:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    from common.getToken import get_token_with_auto_refresh

# 复用与 token 获取一致的 UA/头部风格
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
}

ADDRESS_URL = 'https://xblock-test.charprotocol.com/api/asset/member/wallet/deposit/address'

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


def build_proxy_candidates() -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []

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

    candidates.append({'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'})

    if HAS_SOCKS:
        candidates.append({'http': 'socks5h://127.0.0.1:7891', 'https': 'socks5h://127.0.0.1:7891'})
    else:
        pass

    return candidates


def get_verify_option() -> object:
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
        print('[WARN] 已关闭 TLS 证书校验（仅用于调试，请尽快改回）')
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


def fetch_deposit_address(session: requests.Session, proxies: Dict[str, str], verify_opt: object, token: str,
                          lock_time: int, chain_name: str, wallet_id: int) -> requests.Response:
    headers = dict(BASE_HEADERS)
    # 注意：应用户要求使用小写 authorization 且 scheme 使用小写 bearer
    headers['authorization'] = f'bearer {token}'

    jsessionid = os.getenv('JSESSIONID')
    if jsessionid:
        headers['Cookie'] = f'JSESSIONID={jsessionid}'

    params = {
        'lockTime': str(lock_time),
        'chainName': chain_name,
        'walletId': str(wallet_id),
    }

    timeout_s = float(os.getenv('GETADDR_TIMEOUT', '15'))

    resp = session.get(
        ADDRESS_URL,
        headers=headers,
        params=params,
        proxies=normalize_proxies(proxies),
        timeout=timeout_s,
        allow_redirects=True,
        verify=verify_opt,
    )
    return resp


def get_recharge_address_json(lock_time: Optional[str] = None,
                              chain_name: Optional[str] = None,
                              wallet_id: Optional[str] = None) -> dict:
    """以与脚本相同的代理/证书/认证机制调用地址接口，返回 JSON 数据。
    可通过参数临时覆盖环境变量（若为 None 则使用环境变量或默认值）。
    失败则抛出异常。
    """
    # 覆盖查询参数（通过环境变量传递给 fetch_address）
    if lock_time is not None:
        os.environ['ADDR_LOCK_TIME'] = str(lock_time)
    if chain_name is not None:
        os.environ['ADDR_CHAIN_NAME'] = str(chain_name)
    if wallet_id is not None:
        os.environ['ADDR_WALLET_ID'] = str(wallet_id)

    # 从环境变量获取查询参数的最终值
    lock_time_val = int(os.getenv('ADDR_LOCK_TIME', '0'))
    chain_name_val = os.getenv('ADDR_CHAIN_NAME', 'BTT_TEST')
    wallet_id_val = int(os.getenv('ADDR_WALLET_ID', '127'))

    # 确保从 key.env 读取到可能需要的变量
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

    # 使用更严格的 token 获取封装（带自动刷新）
    token = get_token_for_auth()
    session = requests.Session()
    verify_opt = get_verify_option()
    proxies_list = build_proxy_candidates()

    last_error: Optional[Exception] = None
    for proxies in proxies_list:
        try:
            # 这里调用已定义的 fetch_deposit_address，而不是不存在的 fetch_address
            resp = fetch_deposit_address(session, proxies, verify_opt, token, lock_time_val, chain_name_val, wallet_id_val)
            if resp.ok:
                return resp.json()
            else:
                _ = resp.text[:800]
        except Exception as e:
            last_error = e
            continue
    if last_error:
        raise last_error
    raise RuntimeError('获取充值地址 JSON 失败：所有代理候选均尝试失败')


def batch_get_recharge_address_json(total: int,
                                    lock_time: Optional[str] = None,
                                    chain_name: Optional[str] = None,
                                    wallet_id: Optional[str] = None) -> Tuple[List[dict], List[dict]]:
    """并发批量获取充值地址 JSON，用于高并发压测。

    Args:
        total: 并发请求总数（同样的参数会被请求 total 次）
        lock_time, chain_name, wallet_id: 同 get_recharge_address_json，可临时覆盖。

    Returns:
        (success_list, fail_list)，其中 success_list 每项为响应 JSON，fail_list 每项包含 {"error": str, "status": int | None}
    """
    # 参数覆盖与解析
    if lock_time is not None:
        os.environ['ADDR_LOCK_TIME'] = str(lock_time)
    if chain_name is not None:
        os.environ['ADDR_CHAIN_NAME'] = str(chain_name)
    if wallet_id is not None:
        os.environ['ADDR_WALLET_ID'] = str(wallet_id)

    lock_time_val = int(os.getenv('ADDR_LOCK_TIME', '0'))
    chain_name_val = os.getenv('ADDR_CHAIN_NAME', 'BTT_TEST')
    wallet_id_val = int(os.getenv('ADDR_WALLET_ID', '127'))

    # 环境与鉴权
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

    # 先获取一次 token 供探测阶段使用（实际并发时每次调用都会从缓存/刷新获取）
    token_probe = get_token_for_auth()
    verify_opt = get_verify_option()
    proxies_list = build_proxy_candidates()

    # 先探测可用代理，优先使用第一个可成功响应的代理
    print("🚦 代理可用性探测中...")
    selected_proxies = None
    for idx, p in enumerate(proxies_list, start=1):
        try:
            s = requests.Session()
            r = fetch_deposit_address(s, p, verify_opt, token_probe, lock_time_val, chain_name_val, wallet_id_val)
            if r.ok:
                selected_proxies = p
                print(f"[INFO] 使用代理 #{idx}: {p}")
                break
            else:
                print(f"[WARN] 代理 #{idx} 响应 {r.status_code}")
        except Exception as e:
            print(f"[WARN] 代理 #{idx} 失败: {e}")
            continue
    if selected_proxies is None:
        # 都不可用时仍然采用第一个候选以便返回错误详情
        selected_proxies = proxies_list[0] if proxies_list else {}
        print("[WARN] 未找到可用代理，将使用首个候选继续尝试")

    max_workers = int(os.getenv('GETADDR_MAX_WORKERS', '1'))
    max_workers = max(1, min(max_workers, total))

    print(f"🚀 并发获取充值地址开始 | 请求数: {total} | 并发度: {max_workers}")

    success_list: List[dict] = []
    fail_list: List[dict] = []

    def one_call(idx: int):
        sess = requests.Session()
        try:
            # 每次调用时获取 token（走自动刷新缓存，不会频繁请求），确保长压期间 token 自动滚动
            cur_token = get_token_for_auth()
            resp = fetch_deposit_address(sess, selected_proxies, verify_opt, cur_token, lock_time_val, chain_name_val, wallet_id_val)
            if resp.ok:
                try:
                    data = resp.json()
                except Exception:
                    txt = resp.text[:500]
                    print(f"❌ [{idx}/{total}] 响应非 JSON: {txt}")
                    return ('err', {"error": "non-json", "status": resp.status_code})
                print(f"✅ [{idx}/{total}] 成功")
                return ('ok', data)
            else:
                print(f"❌ [{idx}/{total}] HTTP {resp.status_code}")
                return ('err', {"error": f"HTTP {resp.status_code}", "status": resp.status_code})
        except Exception as e:
            print(f"❌ [{idx}/{total}] 异常: {e}")
            return ('err', {"error": str(e), "status": None})

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(one_call, i + 1) for i in range(total)]
        for fut in as_completed(futures):
            kind, payload = fut.result()
            if kind == 'ok':
                success_list.append(payload)
            else:
                fail_list.append(payload)

    print(f"📊 批量结束：成功 {len(success_list)} / 失败 {len(fail_list)}")
    return success_list, fail_list


def main():
    # 读取 key.env（用于参数和证书、代理设置）
    try:
        from dotenv import load_dotenv  # type: ignore
        if os.path.exists('key.env'):
            load_dotenv('key.env')
    except Exception:
        pass

    # 查询参数（如未设置则使用你示例中的默认值）
    lock_time = int(os.getenv('ADDR_LOCK_TIME', '0'))
    chain_name = os.getenv('ADDR_CHAIN_NAME', 'BTT_TEST')
    wallet_id = int(os.getenv('ADDR_WALLET_ID', '127'))

    # 获取 token（带自动刷新）
    token = get_token_for_auth()
    print('[INFO] 已获取 token（前 30 字符预览）:', token[:30] + '...')

    session = requests.Session()
    verify_opt = get_verify_option()
    print(f"[INFO] TLS verify 模式: {verify_opt}")

    # 支持命令行环境触发批量并发演示：设置 GETADDR_DEMO_BATCH > 0
    demo_batch = int(os.getenv('GETADDR_DEMO_BATCH', '0'))
    if demo_batch > 0:
        batch_get_recharge_address_json(demo_batch, lock_time, chain_name, wallet_id)
        return

    proxies_list = build_proxy_candidates()
    last_error = None
    for idx, proxies in enumerate(proxies_list, start=1):
        try:
            print(f"[INFO] 尝试使用代理 #{idx}: {proxies}")
            resp = fetch_deposit_address(session, proxies, verify_opt, token, lock_time, chain_name, wallet_id)
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


if __name__ == '__main__':
    main()