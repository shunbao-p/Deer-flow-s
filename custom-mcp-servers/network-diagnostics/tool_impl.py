import socket
import json
import subprocess
import sys
from typing import List, Dict, Any
import re


def run_tool(input_text: str) -> str:
    """
    检查主机名的DNS解析结果和TCP端口连通性。
    输入格式: "hostname:port" 或 "hostname"
    如果未指定端口，则默认检查80端口。
    
    返回JSON格式字符串，包含以下字段：
    - host: 原始主机名
    - ipv4_addresses: IPv4地址列表
    - ipv6_addresses: IPv6地址列表  
    - tcp_port: 检查的TCP端口
    - tcp_reachable: 端口是否可达 (true/false)
    - error: 错误信息（如果没有错误则为空字符串）
    """
    result = {
        "host": "",
        "ipv4_addresses": [],
        "ipv6_addresses": [],
        "tcp_port": 0,
        "tcp_reachable": False,
        "error": ""
    }
    
    try:
        # 解析输入：hostname:port 格式
        if ":" in input_text:
            host_part, port_part = input_text.rsplit(":", 1)
            host = host_part.strip()
            try:
                port = int(port_part.strip())
                if port < 1 or port > 65535:
                    raise ValueError("端口必须在1-65535范围内")
            except ValueError as e:
                result["error"] = f"无效的端口号: {port_part} - {str(e)}"
                return json.dumps(result, ensure_ascii=False)
        else:
            host = input_text.strip()
            port = 80  # 默认端口
        
        result["host"] = host
        result["tcp_port"] = port
        
        # DNS解析 - 获取所有地址
        try:
            # 获取地址信息
            addr_info = socket.getaddrinfo(host, port, 
                                         socket.AF_UNSPEC, 
                                         socket.SOCK_STREAM)
            
            ipv4_addrs = []
            ipv6_addrs = []
            
            for info in addr_info:
                addr = info[4][0]  # 获取IP地址
                if ":" in addr:  # IPv6地址
                    if addr not in ipv6_addrs:
                        ipv6_addrs.append(addr)
                else:  # IPv4地址
                    if addr not in ipv4_addrs:
                        ipv4_addrs.append(addr)
            
            result["ipv4_addresses"] = ipv4_addrs
            result["ipv6_addresses"] = ipv6_addrs
            
            if not ipv4_addrs and not ipv6_addrs:
                result["error"] = f"无法解析主机名: {host}"
                return json.dumps(result, ensure_ascii=False)
                
        except socket.gaierror as e:
            result["error"] = f"DNS解析失败: {str(e)}"
            return json.dumps(result, ensure_ascii=False)
        
        # TCP端口连通性检查
        # 尝试连接第一个可用的地址
        tcp_reachable = False
        addresses_to_try = ipv4_addrs + ipv6_addrs
        
        for addr in addresses_to_try:
            try:
                # 根据地址类型创建适当的socket
                if ":" in addr:  # IPv6
                    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                    sock.settimeout(3.0)
                    sock.connect((addr, port))
                else:  # IPv4
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3.0)
                    sock.connect((addr, port))
                
                sock.close()
                tcp_reachable = True
                break
            except (socket.timeout, ConnectionRefusedError, OSError):
                continue  # 尝试下一个地址
        
        result["tcp_reachable"] = tcp_reachable
        
    except Exception as e:
        result["error"] = f"工具执行异常: {str(e)}"
    
    return json.dumps(result, ensure_ascii=False)