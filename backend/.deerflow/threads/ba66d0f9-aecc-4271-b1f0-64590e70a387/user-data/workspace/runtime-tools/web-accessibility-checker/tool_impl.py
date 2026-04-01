import requests
from urllib.parse import urlparse
import json

def run_tool(input_text: str) -> str:
    """
    检查网页可访问性，返回状态码和标题。
    输入: URL字符串
    输出: JSON字符串，包含 original_url, status_code, title, error (如果有)
    """
    url = input_text.strip()
    if not url:
        return json.dumps({
            "error": "URL不能为空"
        }, ensure_ascii=False, indent=2)
    
    # 确保URL有协议头
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        # 设置超时和请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; WebAccessibilityChecker/1.0)'
        }
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        
        # 获取标题
        title = ""
        if 'text/html' in response.headers.get('Content-Type', '').lower():
            # 简单提取<title>标签
            import re
            title_match = re.search(r'<title[^>]*>(.*?)</title>', response.text, re.IGNORECASE | re.DOTALL)
            if title_match:
                title = title_match.group(1).strip()
        
        result = {
            "original_url": input_text,
            "final_url": response.url,
            "status_code": response.status_code,
            "title": title,
            "content_type": response.headers.get('Content-Type', ''),
            "content_length": len(response.content) if response.content else 0,
            "redirect_count": len(response.history) if hasattr(response, 'history') else 0
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except requests.exceptions.Timeout:
        return json.dumps({
            "original_url": input_text,
            "error": "请求超时"
        }, ensure_ascii=False, indent=2)
    except requests.exceptions.ConnectionError:
        return json.dumps({
            "original_url": input_text,
            "error": "连接失败，请检查URL或网络连接"
        }, ensure_ascii=False, indent=2)
    except requests.exceptions.RequestException as e:
        return json.dumps({
            "original_url": input_text,
            "error": f"请求异常: {str(e)}"
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "original_url": input_text,
            "error": f"未知错误: {str(e)}"
        }, ensure_ascii=False, indent=2)