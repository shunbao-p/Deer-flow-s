#!/usr/bin/env python3
"""
主机网络探测脚本
检查指定主机和端口的网络可达性，输出DNS解析和TCP连接状态
"""

import socket
import json
import sys
import concurrent.futures
from typing import List, Dict, Any


def resolve_host(host: str, port: int) -> Dict[str, List[str]]:
    """解析主机的IPv4和IPv6地址"""
    ipv4_addresses = []
    ipv6_addresses = []
    
    try:
        # 获取所有地址信息
        addr_infos = socket.getaddrinfo(
            host, port, 
            family=socket.AF_UNSPEC,  # 同时获取IPv4和IPv6
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP
        )
        
        for addr_info in addr_infos:
            family, _, _, _, sockaddr = addr_info
            ip_addr = sockaddr[0]
            
            if family == socket.AF_INET:
                if ip_addr not in ipv4_addresses:
                    ipv4_addresses.append(ip_addr)
            elif family == socket.AF_INET6:
                if ip_addr not in ipv6_addresses:
                    ipv6_addresses.append(ip_addr)
    
    except socket.gaierror as e:
        # DNS解析失败
        raise Exception(f"DNS解析失败: {e}")
    except Exception as e:
        raise Exception(f"地址解析异常: {e}")
    
    return {
        "ipv4_addresses": ipv4_addresses,
        "ipv6_addresses": ipv6_addresses
    }


def test_tcp_connect(host: str, port: int, timeout: float = 5.0) -> bool:
    """测试TCP端口连接"""
    try:
        # 尝试建立TCP连接
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
    except Exception:
        return False


def probe_host(host: str, port: int, timeout: float = 5.0) -> Dict[str, Any]:
    """主探测函数"""
    result = {
        "host": f"{host}:{port}",
        "ipv4_addresses": [],
        "ipv6_addresses": [],
        "tcp_443_reachable": False,
        "error": None
    }
    
    try:
        # 解析DNS
        dns_result = resolve_host(host, port)
        result["ipv4_addresses"] = dns_result["ipv4_addresses"]
        result["ipv6_addresses"] = dns_result["ipv6_addresses"]
        
        # 测试TCP连接（使用第一个IPv4地址，如果存在的话）
        target_host = host
        if result["ipv4_addresses"]:
            target_host = result["ipv4_addresses"][0]
        elif result["ipv6_addresses"]:
            target_host = result["ipv6_addresses"][0]
        
        result["tcp_443_reachable"] = test_tcp_connect(target_host, port, timeout)
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def main():
    if len(sys.argv) != 3:
        print("用法: python host_probe.py <主机> <端口>")
        print("示例: python host_probe.py openai.com 443")
        sys.exit(1)
    
    host = sys.argv[1]
    port = int(sys.argv[2])
    
    result = probe_host(host, port)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()