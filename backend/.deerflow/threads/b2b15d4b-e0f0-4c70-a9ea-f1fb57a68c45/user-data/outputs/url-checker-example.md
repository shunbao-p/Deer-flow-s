# URL检查工具使用指南

## 工具概述
`url-checker` 是一个运行时创建的MCP工具，用于检查URL并返回详细的HTTP响应信息。

## 已安装工具
- **工具名称**: `url-checker_run_tool`
- **功能**: 检查URL并返回最终跳转地址、HTTP状态码和Content-Type响应头
- **输入**: 一个URL字符串
- **输出**: JSON格式的详细响应信息

## 工具功能
1. **URL重定向跟踪**: 自动跟踪重定向链，显示完整的重定向历史
2. **HTTP状态码检查**: 返回最终的HTTP状态码
3. **Content-Type检测**: 提取响应头的Content-Type信息
4. **错误处理**: 处理网络超时、连接失败等异常情况
5. **详细报告**: 提供完整的响应头信息和重定向历史

## 使用示例

### 示例1: 检查简单URL
```python
# 调用工具
result = url-checker_run_tool("https://httpbin.org/status/200")

# 返回结果示例:
{
  "original_url": "https://httpbin.org/status/200",
  "final_url": "https://httpbin.org/status/200",
  "status_code": 200,
  "content_type": "text/html; charset=utf-8",
  "response_headers": {...},
  "redirect_count": 0,
  "redirect_history": []
}
```

### 示例2: 检查重定向URL
```python
# 调用工具
result = url-checker_run_tool("https://httpbin.org/redirect-to?url=https://httpbin.org/get")

# 返回结果示例:
{
  "original_url": "https://httpbin.org/redirect-to?url=https://httpbin.org/get",
  "final_url": "https://httpbin.org/get",
  "status_code": 200,
  "content_type": "application/json",
  "response_headers": {...},
  "redirect_count": 1,
  "redirect_history": [
    {
      "from": "https://httpbin.org/redirect-to?url=https://httpbin.org/get",
      "to": "https://httpbin.org/get",
      "status_code": 302
    }
  ]
}
```

### 示例3: 检查404页面
```python
# 调用工具
result = url-checker_run_tool("https://httpbin.org/status/404")

# 返回结果示例:
{
  "original_url": "https://httpbin.org/status/404",
  "final_url": "https://httpbin.org/status/404",
  "status_code": 404,
  "content_type": "text/html; charset=utf-8",
  "response_headers": {...},
  "redirect_count": 0,
  "redirect_history": []
}
```

## 错误处理
工具会处理以下错误情况：
- **网络超时**: 请求超时（默认10秒）
- **连接失败**: 无法连接到服务器
- **无效URL**: URL格式错误
- **SSL错误**: SSL证书验证失败

错误响应格式:
```json
{
  "error": "错误描述信息",
  "original_url": "原始URL"
}
```

## 技术实现
- **框架**: 基于FastMCP的stdio服务器
- **HTTP客户端**: 使用requests库
- **重定向处理**: 手动跟踪重定向链，不自动跟随重定向
- **超时设置**: 默认10秒超时
- **用户代理**: 使用自定义User-Agent标识

## 使用场景
1. **URL验证**: 检查URL是否有效和可达
2. **重定向分析**: 分析URL的重定向链
3. **状态码监控**: 监控网站HTTP状态码
4. **内容类型检查**: 验证服务器返回的内容类型
5. **SEO分析**: 分析网站的重定向结构

## 注意事项
1. 工具会发送实际的HTTP请求，请勿用于敏感或私有URL
2. 默认超时时间为10秒，对于慢速网站可能需要调整
3. 工具会跟踪最多10次重定向，防止无限重定向循环
4. 所有请求都包含自定义User-Agent标识

## 工具位置
- **MCP服务器目录**: `/mnt/user-data/workspace/runtime-tools/url-checker/`
- **源代码文件**: 
  - `server.py` - MCP服务器主文件
  - `tool_impl.py` - 工具实现逻辑
  - `requirements.txt` - 依赖包列表
  - `README.md` - 详细文档

## 后续使用
在后续对话中，您可以直接使用 `url-checker_run_tool` 工具来检查任何URL。