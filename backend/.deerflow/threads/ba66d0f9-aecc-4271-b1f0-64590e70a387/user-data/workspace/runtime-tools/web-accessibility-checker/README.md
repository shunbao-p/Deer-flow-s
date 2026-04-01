# Web Accessibility Checker

运行时生成的MCP服务器工具，用于检查网页可访问性。

## 功能

检查给定URL的可访问性，返回HTTP状态码和页面标题。

## 输入

- `input_text`: URL字符串（例如 "https://example.com"）

## 输出

JSON格式的结果，包含：

```json
{
  "original_url": "原始输入的URL",
  "final_url": "最终重定向后的URL",
  "status_code": HTTP状态码,
  "title": "页面标题（如果存在）",
  "content_type": "Content-Type响应头",
  "content_length": 内容长度,
  "redirect_count": 重定向次数
}
```

如果发生错误，返回：

```json
{
  "original_url": "原始输入的URL",
  "error": "错误描述"
}
```

## 示例

输入: `https://example.com`
输出:
```json
{
  "original_url": "https://example.com",
  "final_url": "https://example.com",
  "status_code": 200,
  "title": "Example Domain",
  "content_type": "text/html; charset=UTF-8",
  "content_length": 1256,
  "redirect_count": 0
}
```

## 依赖

- mcp>=1.0.0
- requests>=2.25.0

## 安装

此工具通过运行时工具创建流程自动安装和注册。