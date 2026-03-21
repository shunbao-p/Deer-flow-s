# network-diagnostics MCP Server

用于检查主机名的DNS解析结果（IPv4和IPv6）和指定TCP端口的连通性，输出固定格式的JSON结果。

## 工具说明

### 输入格式
- 字符串格式：`hostname:port` 或 `hostname`
- 示例：`openai.com:443`、`google.com:80`、`github.com`
- 如果未指定端口，默认检查80端口

### 输出格式
返回JSON字符串，包含以下字段：

```json
{
  "host": "原始主机名",
  "ipv4_addresses": ["IPv4地址列表"],
  "ipv6_addresses": ["IPv6地址列表"],
  "tcp_port": 检查的端口号,
  "tcp_reachable": true/false,
  "error": "错误信息（无错误时为空字符串）"
}
```

### 功能说明
1. **DNS解析**：同时解析IPv4和IPv6地址
2. **端口连通性检查**：尝试连接到解析出的地址，3秒超时
3. **错误处理**：如果DNS解析失败或输入格式错误，返回相应的错误信息

## 使用场景
- 网络故障排查
- 服务健康检查
- DNS解析验证
- 端口开放状态确认

## 安装和运行
作为MCP服务器运行，通过stdio传输协议与DeerFlow代理集成。