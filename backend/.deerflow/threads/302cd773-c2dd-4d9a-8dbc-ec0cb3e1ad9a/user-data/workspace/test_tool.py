#!/usr/bin/env python3
import sys
sys.path.insert(0, '/mnt/user-data/workspace/runtime-tools/network-diagnostics')

from tool_impl import run_tool

# 测试基本功能
test_cases = [
    "localhost:80",
    "127.0.0.1:8080",
    "openai.com:443",
    "example.com",
    "invalid-host-xyz-123:80"
]

for test_input in test_cases:
    print(f"\n测试输入: {test_input}")
    try:
        result = run_tool(test_input)
        print(f"结果: {result}")
    except Exception as e:
        print(f"错误: {e}")