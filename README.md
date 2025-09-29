# XBlock 接口压力测试工具

这是一个用于测试 XBlock 区块链接口性能的 Python 压力测试工具，支持充值、提币和地址获取等核心功能的并发压测。

## 🚀 功能特性

### 核心功能
- **充值压测**: 支持 BTT 代币批量转账压测
- **提币压测**: 支持提币交易接口并发测试
- **地址获取压测**: 支持充值地址获取接口性能测试

### 压测模式
- **固定模式**: 固定 TPS/QPS 持续压测
- **阶梯模式**: 从起始并发逐步增加到目标并发

### 技术特性
- 支持多种代理配置（HTTP/SOCKS5）
- 自动 Token 获取与刷新
- 并发执行与性能优化
- 详细的日志记录与统计
- 环境变量配置支持

## 📁 项目结构

```
xblock_interface_pressure_test/
├── main.py                 # 主程序入口
├── key.env                 # 环境配置文件
├── common/                 # 公共模块
│   └── getToken.py        # Token 获取与认证
├── recharge/              # 充值相关模块
│   ├── recharge_stress.py # 充值压测逻辑
│   ├── address_stress.py  # 地址获取压测
│   ├── sendTx.py          # BTT 转账发送
│   └── getAddress.py      # 充值地址获取
├── withdrawal/            # 提币相关模块
│   └── sendTx.py          # 提币交易发送
├── log/                   # 日志目录
│   ├── transfer_log.json  # 转账日志
│   └── send_txlog.json    # 提币日志
└── reports/               # 测试报告
    ├── junit.xml
    └── pytest_report.html
```

## 🛠️ 环境配置

### 1. 安装依赖

```bash
pip install web3 requests python-dotenv
```

可选依赖（用于 SOCKS5 代理支持）：
```bash
pip install PySocks
```

### 2. 配置环境变量

创建或编辑 `key.env` 文件：

```env
# 区块链配置
PRIVATE_KEY=your_private_key_here
BTT_RPC_URL=https://pre-rpc.bt.io

# API 认证配置
API_USERNAME=your_username
API_PASSWORD=your_password
API_CLIENT_ID=
API_CLIENT_SECRET=
# 代理配置（可选）
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890

# TLS 配置（调试用）
DISABLE_TLS_VERIFY=1

# 充值配置
RECHARGE_AMOUNT_BTT=0.007
RECHARGE_TARGET_ADDRESS=

# 地址获取配置
ADDR_LOCK_TIME=0
ADDR_CHAIN_NAME=BTT_TEST
ADDR_WALLET_ID=127

# 提币配置
WD_WALLET_ID=118
WD_CHAIN_NAME=BTT_TEST
WD_FROM_ADDRESS=
WD_TO_ADDRESS=
WD_TOKEN_ADDRESS=
WD_AMOUNT=7
```

## 🎯 使用方法

### 启动主程序

```bash
python main.py
```

程序会显示菜单选项：

```
请选择要执行的操作:
1) 充值完整流程压测
2) 提币完整流程压测
3) 地址获取接口压测（独立）
0) 退出
```

### 1. 充值压测

选择模式：
- **固定模式**: 固定 TPS 持续指定秒数
- **阶梯模式**: 从起始 TPS 逐步增加到结束 TPS

配置参数：
- TPS: 每秒交易数
- 持续秒数: 压测持续时间
- 金额: 每笔转账的 BTT 数量

### 2. 提币压测

配置提币参数：
- walletId: 钱包 ID
- chainName: 链名称
- fromAddress: 发送地址
- toAddress: 接收地址
- tokenAddress: 代币地址（空表示原生代币）
- amount: 转账金额

### 3. 地址获取压测

测试充值地址获取接口的性能：
- 支持固定并发和阶梯并发模式
- 可配置锁定期、链名称、钱包 ID 等参数

## ⚙️ 高级配置

### 环境变量说明

#### 充值相关
- `RECHARGE_AMOUNT_BTT`: 每笔充值金额（默认 0.007）
- `RECHARGE_TPS`: 默认 TPS（默认 1）
- `RECHARGE_DURATION`: 默认持续秒数（默认 10）
- `RECHARGE_START_TPS`: 阶梯模式起始 TPS（默认 1）
- `RECHARGE_END_TPS`: 阶梯模式结束 TPS（默认 5）
- `RECHARGE_STEP_DURATION`: 每阶段持续秒数（默认 5）

#### 地址获取相关
- `ADDR_QPS`: 默认 QPS（默认 10）
- `ADDR_DURATION`: 默认持续秒数（默认 10）
- `ADDR_START_CONCURRENCY`: 起始并发（默认 1）
- `ADDR_END_CONCURRENCY`: 结束并发（默认 10）
- `ADDR_STEP_DURATION`: 每阶段持续秒数（默认 5）
- `GETADDR_MAX_WORKERS`: 最大工作线程数

#### 提币相关
- `WD_QPS`: 默认 QPS（默认 10）
- `WD_DURATION`: 默认持续秒数（默认 10）
- `WD_START_CONCURRENCY`: 起始并发（默认 1）
- `WD_END_CONCURRENCY`: 结束并发（默认 10）
- `WD_STEP_DURATION`: 每阶段持续秒数（默认 5）
- `WD_MAX_WORKERS`: 最大工作线程数

#### 网络配置
- `SENDTX_MAX_WORKERS`: 转账最大工作线程数
- `SENDTX_POOL_MAXSIZE`: HTTP 连接池大小（默认 64）
- `FIXED_GAS_PRICE_GWEI`: 固定 Gas 价格（Gwei）
- `ESTIMATE_GAS`: 是否启用 Gas 估算（0/1）
- `TOKEN_REFRESH_INTERVAL_SEC`: Token 刷新间隔（默认 300 秒）

### 代理配置

支持多种代理方式：

1. **环境变量代理**:
   ```bash
   export HTTP_PROXY=http://127.0.0.1:7890
   export HTTPS_PROXY=http://127.0.0.1:7890
   ```

2. **Clash 代理**（自动检测）:
   - HTTP: `http://127.0.0.1:7890`
   - SOCKS5: `socks5h://127.0.0.1:7891`

3. **自定义代理**:
   在 `key.env` 中配置 `HTTP_PROXY` 和 `HTTPS_PROXY`

## 📊 日志与报告

### 日志文件

- `log/transfer_log.json`: 充值转账日志
- `log/send_txlog.json`: 提币交易日志

### 日志格式

**转账日志示例**:
```json
{
  "successful": [
    {
      "index": 1,
      "to": "",
      "tx_hash": "0x...",
      "gas": 21000,
      "gas_price_gwei": 50.0,
      "value_btt": 0.007,
      "nonce": 123,
      "timestamp": 1640995200
    }
  ],
  "failed": []
}
```

**提币日志示例**:
```json
{
  "code": 200,
  "message": "Success",
  "timestamp": 1757044079779,
  "data": {
    "assetSendId": 1865
  }
}
```

## 🔧 独立模块使用

### 单独运行充值转账

```bash
python recharge/sendTx.py --recipient 0x... --count 10 --amount 0.007
```

### 单独运行地址获取

```bash
python recharge/getAddress.py
```

### 单独运行提币发送

```bash
python withdrawal/sendTx.py
```

## 🚨 注意事项

1. **私钥安全**: 请妥善保管 `key.env` 文件中的私钥，不要提交到版本控制系统
2. **网络配置**: 确保代理配置正确，特别是在网络受限环境中
3. **Gas 费用**: 注意设置合适的 Gas 价格，避免交易失败
4. **并发控制**: 根据服务器性能调整并发参数，避免过载
5. **测试环境**: 建议在测试网络上进行压测，避免影响主网

## 🐛 故障排除

### 常见问题

1. **Token 获取失败**:
   - 检查用户名密码配置
   - 确认代理设置正确
   - 验证网络连接

2. **交易发送失败**:
   - 检查私钥和地址配置
   - 确认账户余额充足
   - 验证 RPC 节点连接

3. **代理连接问题**:
   - 确认代理服务运行正常
   - 检查端口配置
   - 尝试不同的代理类型

### 调试模式

设置环境变量启用详细日志：
```bash
export DISABLE_TLS_VERIFY=1  # 关闭 TLS 验证（仅调试用）
export ESTIMATE_GAS=1        # 启用 Gas 估算
```

## 📈 性能优化

1. **并发调优**: 根据系统性能调整 `MAX_WORKERS` 参数
2. **连接池**: 调整 `SENDTX_POOL_MAXSIZE` 优化网络连接
3. **Gas 策略**: 使用固定 Gas 价格避免动态估算开销
4. **代理选择**: 选择延迟最低的代理服务器

## 📝 更新日志

- **v1.0.0**: 初始版本，支持充值、提币、地址获取压测
- 支持固定和阶梯两种压测模式
- 集成代理支持和自动 Token 管理
- 完善的日志记录和错误处理

## 📄 许可证

本项目仅供学习和测试使用，请遵守相关法律法规和服务条款。
