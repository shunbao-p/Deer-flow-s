#!/usr/bin/env python3
import sys
import json
import subprocess

def test_url_checker():
    """测试URL检查工具"""
    
    # 测试用例
    test_cases = [
        "https://httpbin.org/status/200",
        "https://httpbin.org/redirect-to?url=https://httpbin.org/get",
        "https://httpbin.org/status/404",
    ]
    
    print("测试URL检查工具...")
    print("=" * 60)
    
    for url in test_cases:
        print(f"\n测试URL: {url}")
        print("-" * 40)
        
        try:
            # 导入工具实现并直接调用
            sys.path.insert(0, '/mnt/user-data/workspace/runtime-tools/url-checker')
            from tool_impl import run_tool
            
            result = run_tool(url)
            data = json.loads(result)
            
            if "error" in data:
                print(f"错误: {data['error']}")
            else:
                print(f"原始URL: {data['original_url']}")
                print(f"最终URL: {data['final_url']}")
                print(f"状态码: {data['status_code']}")
                print(f"Content-Type: {data['content_type']}")
                print(f"重定向次数: {data['redirect_count']}")
                
                if data['redirect_history']:
                    print("重定向历史:")
                    for i, redirect in enumerate(data['redirect_history'], 1):
                        print(f"  {i}. {redirect['from']} → {redirect['to']} (状态码: {redirect['status_code']})")
                        
        except Exception as e:
            print(f"测试失败: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成！")

if __name__ == "__main__":
    test_url_checker()