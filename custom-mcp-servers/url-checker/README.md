# URL Checker MCP Server

一个用于检查URL的MCP服务器工具，返回最终跳转地址、HTTP状态码和Content-Type响应头。

## 功能

- 输入一个URL，自动跟踪重定向链
- 返回最终跳转地址
- 返回HTTP状态码
- 返回Content-Type响应头
- 返回完整的响应头信息
- 显示重定向历史记录

## 输入格式

纯文本URL字符串，例如：
```
https://example.com
```

## 输出格式

JSON格式，包含以下字段：

```json
{
  "original_url": "原始URL",
  "final_url": "最终跳转地址",
  "status_code": HTTP状态码,
  "content_type": "Content-Type响应头",
  "headers": "所有响应头",
  "redirect_history": "重定向历史记录",
  "redirect_count": "重定向次数"
}
```

## 错误处理

如果发生错误，返回包含错误信息的JSON：

```json
{
  "original_url": "URL",
  "error": "错误描述"
}
```

## 使用示例

```python
# 检查URL
result = run_tool("https://example.com")
```

## 依赖

- Python 3.8+
- requests>=2.31.0
- mcp>=1.0.0