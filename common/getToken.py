import os
import json
import sys
from typing import Dict, List, Optional, Tuple
import requests
import time
import threading

TOKEN_URL = 'https://xblock-test.charprotocol.com/api/security/oauth2/token'

# 与你在 curl/浏览器一致的请求头（删掉了会干扰的 Accept-Encoding，其他保持相对保守）
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

# 使用 multipart/form-data（等价 curl 的 -F），如需改为 x-www-form-urlencoded 将此置为 False
USE_MULTIPART = True

# 账户信息（可在 key.env 覆盖：API_USERNAME 等）
USERNAME = ''
PASSWORD = ''
CLIENT_ID = ''
CLIENT_SECRET = ''
GRANT_TYPE = ''

# 探测 SOCKS 支持
try:
    import socks  # type: ignore
    HAS_SOCKS = True
except Exception:
    HAS_SOCKS = False

# 新增：token 缓存（按时间间隔自动刷新）
_TOKEN_CACHE: Dict[str, Optional[str]] = {'value': None, 'ts': 0.0}
_TOKEN_LOCK = threading.Lock()


def normalize_url(u: Optional[str]) -> Optional[str]:
    if not u:
        return u
    u = u.strip()
    if not u:
        return None
    # 若未显式指定 scheme，按 http 代理补齐
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
    """构造代理候选列表：优先系统环境变量 -> Clash 常见端口 7890(HTTP)。若安装 PySocks 再尝试 SOCKS5h。"""
    candidates: List[Dict[str, str]] = []

    # 1) 来自环境变量（去空格）
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

    # 2) Clash/Clash Verge 常见本地端口（HTTP 代理）
    candidates.append({'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'})

    # 3) SOCKS5h（仅当已安装 PySocks）
    if HAS_SOCKS:
        candidates.append({'http': 'socks5h://127.0.0.1:7891', 'https': 'socks5h://127.0.0.1:7891'})
    else:
        pass

    return candidates


def build_payload() -> Tuple[Optional[Dict[str, tuple]], Optional[Dict[str, str]]]:
    """根据 USE_MULTIPART 选择 multipart/form-data 或 application/x-www-form-urlencoded 的负载。"""
    if USE_MULTIPART:
        files = {
            'username': (None, USERNAME),
            'password': (None, PASSWORD),
            'client_id': (None, CLIENT_ID),
            'client_secret': (None, CLIENT_SECRET),
            'grant_type': (None, GRANT_TYPE),
        }
        return files, None
    else:
        data = {
            'username': USERNAME,
            'password': PASSWORD,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': GRANT_TYPE,
        }
        return None, data


def get_verify_option() -> object:
    """决定 requests 的 verify 参数：
    优先使用可用证书文件（REQUESTS_CA_BUNDLE/SSL_CERT_FILE/CURL_CA_BUNDLE/PROXY_CA_BUNDLE），
    若设置 DISABLE_TLS_VERIFY=1 则关闭校验（仅调试用）。
    默认 True。
    """
    # 可由 key.env 提供自定义证书路径
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


def try_fetch_token(session: requests.Session, proxies: Dict[str, str], verify_opt: object) -> requests.Response:
    files, data = build_payload()
    # 不强制 Content-Type，requests 会根据 files/data 正确设置
    resp = session.post(
        TOKEN_URL,
        headers=BASE_HEADERS,
        files=files,
        data=data,
        proxies=normalize_proxies(proxies),
        timeout=30,
        allow_redirects=True,
        verify=verify_opt,
    )
    return resp


# 新增：供其他模块直接获取 token 的函数（无缓存，立即请求）
def get_token() -> str:
    """获取 access_token 并返回字符串。抛出异常表示失败。"""
    # 从 key.env 读取配置（如存在）
    try:
        from dotenv import load_dotenv  # type: ignore
        if os.path.exists('key.env'):
            load_dotenv('key.env')
            global USERNAME, PASSWORD, CLIENT_ID, CLIENT_SECRET, GRANT_TYPE
            USERNAME = os.getenv('API_USERNAME', USERNAME)
            PASSWORD = os.getenv('API_PASSWORD', PASSWORD)
            CLIENT_ID = os.getenv('API_CLIENT_ID', CLIENT_ID)
            CLIENT_SECRET = os.getenv('API_CLIENT_SECRET', CLIENT_SECRET)
            GRANT_TYPE = os.getenv('API_GRANT_TYPE', GRANT_TYPE)
    except Exception:
        pass

    session = requests.Session()
    verify_opt = get_verify_option()
    proxies_list = build_proxy_candidates()

    last_error: Optional[Exception] = None
    for proxies in proxies_list:
        try:
            resp = try_fetch_token(session, proxies, verify_opt)
            if resp.ok:
                data = resp.json()
                token = data.get('access_token') or data.get('token') or data.get('data', {}).get('access_token')
                if not token:
                    raise RuntimeError('响应中未找到 access_token 字段')
                return token
            else:
                # 尝试读取错误内容帮助定位
                _ = resp.text[:300]
        except Exception as e:
            last_error = e
            continue

    if last_error:
        raise last_error
    raise RuntimeError('获取 token 失败：代理尝试均未成功')


# 新增：带缓存与定时刷新（默认每 300s 可通过 TOKEN_REFRESH_INTERVAL_SEC 配置）
def get_token_with_auto_refresh(refresh_interval_sec: Optional[int] = None) -> str:
    interval = int(os.getenv('TOKEN_REFRESH_INTERVAL_SEC', str(refresh_interval_sec if refresh_interval_sec is not None else 300)))
    now = time.time()
    val = _TOKEN_CACHE.get('value')
    ts = float(_TOKEN_CACHE.get('ts') or 0.0)
    if val and (now - ts) < interval:
        return val  # 命中缓存
    with _TOKEN_LOCK:
        # 双重检查，避免并发刷新
        now2 = time.time()
        val2 = _TOKEN_CACHE.get('value')
        ts2 = float(_TOKEN_CACHE.get('ts') or 0.0)
        if val2 and (now2 - ts2) < interval:
            return val2
        # 重新获取并更新缓存
        fresh = get_token()
        _TOKEN_CACHE['value'] = fresh
        _TOKEN_CACHE['ts'] = time.time()
        return fresh


def main():
    # 可选：从 key.env 读取（若存在则覆盖上面的常量或提供 PROXY_CA_BUNDLE、DISABLE_TLS_VERIFY 等）
    try:
        from dotenv import load_dotenv  # type: ignore
        if os.path.exists('key.env'):
            load_dotenv('key.env')
            global USERNAME, PASSWORD, CLIENT_ID, CLIENT_SECRET, GRANT_TYPE
            USERNAME = os.getenv('API_USERNAME', USERNAME)
            PASSWORD = os.getenv('API_PASSWORD', PASSWORD)
            CLIENT_ID = os.getenv('API_CLIENT_ID', CLIENT_ID)
            CLIENT_SECRET = os.getenv('API_CLIENT_SECRET', CLIENT_SECRET)
            GRANT_TYPE = os.getenv('API_GRANT_TYPE', GRANT_TYPE)
    except Exception:
        pass

    session = requests.Session()

    verify_opt = get_verify_option()
    print(f"[INFO] TLS verify 模式: {verify_opt}")

    proxies_list = build_proxy_candidates()
    last_error = None
    for idx, proxies in enumerate(proxies_list, start=1):
        try:
            print(f"[INFO] 尝试使用代理 #{idx}: {proxies}")
            resp = try_fetch_token(session, proxies, verify_opt)
            content_type = resp.headers.get('Content-Type', '')
            print(f"[INFO] HTTP {resp.status_code}, Content-Type: {content_type}")

            # 成功
            if resp.ok:
                try:
                    data = resp.json()
                except Exception:
                    print('[ERROR] 响应不是 JSON：\n' + resp.text[:500])
                    sys.exit(2)

                # 尝试读取常见字段
                access_token = data.get('access_token') or data.get('token') or data.get('data', {}).get('access_token')
                if access_token:
                    print('[SUCCESS] 获取到 access_token:')
                    print(access_token)
                else:
                    print('[WARN] 未找到 access_token 字段，完整响应为:')
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                return

            # 非 2xx
            body_preview = resp.text[:800]
            print(f"[WARN] 请求失败，状态码: {resp.status_code}\n响应内容预览:\n{body_preview}")

        except Exception as e:
            last_error = e
            print(f"[ERROR] 代理 {proxies} 访问失败：{e}")
            continue

    print('\n[FAIL] 所有代理候选均尝试失败。请确认你的代理（Clash/V2Ray 等）已启动且本地端口正确，或设置环境变量 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY 后再试。')
    if last_error:
        print(f"最后错误: {repr(last_error)}")
    sys.exit(1)


if __name__ == '__main__':
    main()
