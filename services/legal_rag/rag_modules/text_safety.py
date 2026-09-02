"""
文本安全处理工具。
用于清洗终端输入中可能混入的非法代理字符，避免 UTF-8 编码链路异常。
"""

from typing import Any


def has_surrogates(text: str) -> bool:
    """检测字符串中是否包含 Unicode 代理区字符。"""
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def sanitize_query_text(raw_text: Any) -> str:
    """
    清洗查询文本，确保可安全进入 LLM / Neo4j / 向量检索链路。

    处理策略：
    1) 非字符串输入转字符串；
    2) 去除代理区字符（U+D800~U+DFFF）；
    3) 去除 NUL 字符；
    4) 通过 UTF-8 ignore 再做一次安全过滤。
    """
    if raw_text is None:
        return ""

    text = raw_text if isinstance(raw_text, str) else str(raw_text)
    text = "".join(ch for ch in text if not (0xD800 <= ord(ch) <= 0xDFFF))
    text = text.replace("\x00", "")
    text = text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
    return text.strip()

