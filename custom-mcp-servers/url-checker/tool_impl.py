import requests
from typing import Dict, Any
import json


def run_tool(input_text: str) -> str:
    """
    检查URL并返回最终跳转地址、HTTP状态码和Content-Type响应头
    
    参数:
        input_text: 要检查的URL字符串
    
    返回:
        JSON格式字符串，包含:
        - original_url: 原始URL
        - final_url: 最终跳转地址
        - status_code: HTTP状态码
        - content_type: Content-Type响应头
        - headers: 所有响应头
        - error: 错误信息（如果有）
    """
    url = input_text.strip()
    
    # 验证URL格式
    if not url.startswith(('http://', 'https://')):
        return json.dumps({
            "original_url": url,
            "error": "URL必须以http://或https://开头"
        }, ensure_ascii=False, indent=2)
    
    try:
        # 设置请求头，模拟浏览器请求
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # 发送请求，不自动跳转，以便跟踪重定向
        response = requests.get(
            url, 
            headers=headers, 
            allow_redirects=False,
            timeout=10
        )
        
        # 处理重定向
        redirect_history = []
        current_response = response
        
        while current_response.status_code in (301, 302, 303, 307, 308):
            redirect_url = current_response.headers.get('Location')
            if not redirect_url:
                break
                
            # 处理相对URL
            if redirect_url.startswith('/'):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                redirect_url = base_url + redirect_url
            elif not redirect_url.startswith(('http://', 'https://')):
                # 处理相对路径
                from urllib.parse import urljoin
                redirect_url = urljoin(url, redirect_url)
            
            redirect_history.append({
                "from": url if not redirect_history else redirect_history[-1]["to"],
                "to": redirect_url,
                "status_code": current_response.status_code
            })
            
            # 跟随重定向
            current_response = requests.get(
                redirect_url,
                headers=headers,
                allow_redirects=False,
                timeout=10
            )
        
        # 构建结果
        result = {
            "original_url": url,
            "final_url": redirect_history[-1]["to"] if redirect_history else url,
            "status_code": current_response.status_code,
            "content_type": current_response.headers.get('Content-Type', ''),
            "headers": dict(current_response.headers),
            "redirect_history": redirect_history,
            "redirect_count": len(redirect_history)
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except requests.exceptions.Timeout:
        return json.dumps({
            "original_url": url,
            "error": "请求超时（10秒）"
        }, ensure_ascii=False, indent=2)
        
    except requests.exceptions.ConnectionError:
        return json.dumps({
            "original_url": url,
            "error": "连接失败，请检查URL或网络连接"
        }, ensure_ascii=False, indent=2)
        
    except requests.exceptions.RequestException as e:
        return json.dumps({
            "original_url": url,
            "error": f"请求异常: {str(e)}"
        }, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({
            "original_url": url,
            "error": f"未知错误: {str(e)}"
        }, ensure_ascii=False, indent=2)