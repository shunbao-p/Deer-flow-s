#!/usr/bin/env python3
"""
报销审核卡技能 - 将原始报销材料整理成标准化的报销审核卡

功能：
1. 解析原始报销记录（从发票、报销单、聊天记录、截图OCR等提取）
2. 提取关键字段：单据编号、报销人、日期、金额、费用类型、说明等
3. 应用审核规则检查合规性、完整性、风险
4. 生成标准化的报销审核卡表格
"""

import re
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import json

class ExpenseAuditCardSkill:
    """报销审核卡技能主类"""
    
    def __init__(self):
        # 字段映射：原始文本中的关键词 -> 字段名
        self.field_patterns = {
            "单据编号": r"(单号|编号|单据)[：:]?\s*([A-Z0-9-]+)",
            "报销人": r"(报销人|申请人)[：:]?\s*([\u4e00-\u9fa5]{2,4})",
            "日期": r"(日期|时间)[：:]?\s*(\d{4}-\d{2}-\d{2})",
            "金额": r"(金额|费用)[：:]?\s*(\d+(?:\.\d+)?)",
            "费用类型": r"(类型|类别)[：:]?\s*([\u4e00-\u9fa5]+)",
            "说明": r"(说明|事由|用途)[：:]?\s*([^\n]+)",
            "参与人": r"(参与人|参与人员)[：:]?\s*([^\n]+)",
            "出发地": r"(出发地|起点)[：:]?\s*([^\n]+)",
            "目的地": r"(目的地|终点)[：:]?\s*([^\n]+)",
            "发票状态": r"(发票|票据)[：:]?\s*([^\n]+)",
        }
        
    def parse_expense_record(self, record_text: str) -> Dict[str, Any]:
        """解析单条报销记录"""
        record = {
            "单据编号": "缺失",
            "报销人": "缺失", 
            "日期": "缺失",
            "金额": 0.0,
            "费用类型": "缺失",
            "说明": "缺失",
            "参与人": "缺失",
            "出发地": "缺失",
            "目的地": "缺失",
            "发票状态": "缺失",
            "原始文本": record_text
        }
        
        # 使用正则表达式提取字段
        for field_name, pattern in self.field_patterns.items():
            match = re.search(pattern, record_text)
            if match:
                if field_name == "金额":
                    try:
                        record[field_name] = float(match.group(2))
                    except ValueError:
                        record[field_name] = 0.0
                else:
                    record[field_name] = match.group(2).strip()
        
        # 特殊处理：从"记录X："格式中提取基础信息
        if record["单据编号"] == "缺失":
            # 尝试从文本开头提取编号
            match = re.search(r"([A-Z]{2}-\d{4}-\d{3})", record_text)
            if match:
                record["单据编号"] = match.group(1)
                
        if record["报销人"] == "缺失":
            # 尝试从文本中提取常见中文姓名
            match = re.search(r"[\u4e00-\u9fa5]{2,4}[\u4e00-\u9fa5]*", record_text.split("，")[0])
            if match and "记录" not in match.group():
                record["报销人"] = match.group()
                
        if record["金额"] == 0.0:
            # 尝试提取数字作为金额
            match = re.search(r"金额?\s*(\d+)", record_text)
            if match:
                try:
                    record["金额"] = float(match.group(1))
                except ValueError:
                    pass
                    
        if record["费用类型"] == "缺失":
            # 尝试识别费用类型关键词
            type_keywords = ["餐饮", "打车", "交通", "办公用品", "差旅", "住宿", "会议"]
            for keyword in type_keywords:
                if keyword in record_text:
                    record["费用类型"] = keyword
                    break
                    
        return record
    
    def check_completeness(self, record: Dict[str, Any]) -> Tuple[str, List[str]]:
        """检查票据完整性"""
        missing_fields = []
        
        if record["日期"] == "缺失":
            missing_fields.append("日期")
        if record["金额"] == 0.0 or record["金额"] == "缺失":
            missing_fields.append("金额")
        if record["报销人"] == "缺失":
            missing_fields.append("报销人")
            
        if missing_fields:
            return "不完整", missing_fields
        else:
            return "完整", []
    
    def check_compliance(self, record: Dict[str, Any]) -> Tuple[str, List[str]]:
        """检查是否符合规则"""
        violations = []
        
        # 餐饮类报销规则：需要有参与人或事由说明
        if record["费用类型"] == "餐饮":
            if record["参与人"] == "缺失" and ("参与人" in record["原始文本"] and "无" in record["原始文本"]):
                violations.append("餐饮类报销缺少参与人信息")
            if record["说明"] == "缺失" or "聚餐" not in record["说明"]:
                violations.append("餐饮类报销缺少明确事由说明")
                
        # 打车类报销规则：需要有出发地和目的地
        if record["费用类型"] in ["打车", "交通"]:
            if record["出发地"] == "缺失":
                violations.append("打车类报销缺少出发地")
            if record["目的地"] == "缺失":
                violations.append("打车类报销缺少目的地")
                
        # 金额>1000且没有明确业务事由
        if record["金额"] > 1000:
            if record["说明"] == "缺失" or len(record["说明"].strip()) < 5:
                violations.append("金额大于1000但缺少明确业务事由")
                
        if violations:
            return "不符合", violations
        else:
            return "符合", []
    
    def check_duplicate_risk(self, records: List[Dict[str, Any]], current_index: int) -> Tuple[str, str]:
        """检查是否存在重复报销风险"""
        current_record = records[current_index]
        
        for i, record in enumerate(records):
            if i == current_index:
                continue
                
            # 检查同一报销人、同一天、同金额、相似用途
            if (record["报销人"] == current_record["报销人"] and
                record["日期"] == current_record["日期"] and
                abs(record["金额"] - current_record["金额"]) < 1.0 and
                record["费用类型"] == current_record["费用类型"]):
                
                # 用途相似性检查
                if (record["说明"] != "缺失" and current_record["说明"] != "缺失" and
                    any(word in current_record["说明"] for word in ["聚餐", "晚餐", "午餐", "会议", "拜访"])):
                    return "存在", f"与记录{i+1}可能存在重复报销"
                    
        return "不存在", ""
    
    def check_manual_review(self, record: Dict[str, Any], compliance_violations: List[str]) -> Tuple[bool, List[str]]:
        """检查是否需要人工复核"""
        reasons = []
        needs_review = False
        
        # 规则：金额 > 1000 且没有明确业务事由
        if record["金额"] > 1000 and ("金额大于1000但缺少明确业务事由" in compliance_violations or record["说明"] == "缺失"):
            reasons.append("金额大于1000且缺少明确业务事由")
            needs_review = True
            
        # 规则：打车类报销没有出发地或目的地
        if record["费用类型"] in ["打车", "交通"]:
            if record["出发地"] == "缺失":
                reasons.append("打车类报销缺少出发地")
                needs_review = True
            if record["目的地"] == "缺失":
                reasons.append("打车类报销缺少目的地")
                needs_review = True
                
        # 如果有任何合规性问题，可能需要人工复核
        if compliance_violations:
            needs_review = True
            
        return needs_review, reasons
    
    def determine_final_conclusion(self, completeness: str, compliance: str, 
                                 needs_manual_review: bool, manual_review_reasons: List[str]) -> str:
        """确定最终审核结论"""
        if completeness == "不完整":
            return "需人工复核"
            
        if compliance == "不符合":
            return "不通过"
            
        if needs_manual_review:
            return "需人工复核"
            
        return "通过"
    
    def generate_audit_card(self, records: List[Dict[str, Any]]) -> str:
        """生成报销审核卡表格"""
        table_rows = []
        
        for i, record in enumerate(records):
            # 检查各项
            completeness_status, missing_fields = self.check_completeness(record)
            compliance_status, violations = self.check_compliance(record)
            duplicate_risk, duplicate_reason = self.check_duplicate_risk(records, i)
            needs_review, review_reasons = self.check_manual_review(record, violations)
            
            # 确定最终结论
            final_conclusion = self.determine_final_conclusion(
                completeness_status, compliance_status, needs_review, review_reasons
            )
            
            # 构建人工复核原因
            manual_review_reason = ""
            if review_reasons:
                manual_review_reason = "；".join(review_reasons)
            elif needs_review and final_conclusion == "需人工复核":
                manual_review_reason = "系统规则触发需要人工复核"
            else:
                manual_review_reason = "无"
                
            # 格式化金额
            amount_display = f"{record['金额']:.0f}" if record['金额'] > 0 else "缺失"
            
            # 构建表格行
            row = [
                record["单据编号"],
                record["报销人"],
                record["日期"],
                amount_display,
                record["费用类型"],
                completeness_status,
                duplicate_risk,
                compliance_status,
                manual_review_reason,
                final_conclusion
            ]
            table_rows.append(row)
        
        # 生成Markdown表格
        headers = ["单据编号", "报销人", "日期", "金额", "费用类型", "票据是否完整", 
                  "是否存在重复报销风险", "是否符合规则", "需要人工复核的原因", "最终审核结论"]
        
        table_lines = []
        table_lines.append("| " + " | ".join(headers) + " |")
        table_lines.append("|" + "|".join(["---"] * len(headers)) + "|")
        
        for row in table_rows:
            table_lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
        
        return "\n".join(table_lines)
    
    def process_expense_records(self, input_text: str) -> str:
        """处理原始报销材料"""
        # 分割记录
        records = []
        lines = input_text.strip().split('\n')
        
        current_record = []
        for line in lines:
            line = line.strip()
            if re.match(r'^记录\d+[：:]', line):
                if current_record:
                    records.append('\n'.join(current_record))
                    current_record = []
            current_record.append(line)
        
        if current_record:
            records.append('\n'.join(current_record))
        
        # 如果没有检测到"记录X："格式，尝试其他分割方式
        if len(records) <= 1 and "记录" not in input_text:
            records = [input_text]
        
        # 解析每条记录
        parsed_records = []
        for record_text in records:
            parsed_record = self.parse_expense_record(record_text)
            parsed_records.append(parsed_record)
        
        # 生成审核卡
        audit_card = self.generate_audit_card(parsed_records)
        
        # 添加说明
        output = "# 报销审核卡\n\n"
        output += "**处理时间：** " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n"
        output += "**审核规则摘要：**\n"
        output += "1. 缺少日期、金额、报销人任一字段 → 票据不完整\n"
        output += "2. 餐饮类报销缺少参与人或事由说明 → 不符合规则\n"
        output += "3. 金额>1000且缺少明确业务事由 → 需要人工复核\n"
        output += "4. 打车类报销缺少出发地或目的地 → 需要人工复核\n"
        output += "5. 同一报销人、同一天、同金额、相似用途 → 存在重复报销风险\n\n"
        output += "## 审核结果\n\n"
        output += audit_card + "\n\n"
        output += "---\n"
        output += "*注：此审核结果基于系统规则自动生成，仅供参考。最终审核结果以财务部门确认为准。*"
        
        return output


def skill_main(input_text: str) -> str:
    """
    报销审核卡技能主函数
    
    Args:
        input_text: 原始报销材料文本
        
    Returns:
        标准化的报销审核卡（Markdown格式）
    """
    skill = ExpenseAuditCardSkill()
    return skill.process_expense_records(input_text)


if __name__ == "__main__":
    # 测试数据
    test_input = """记录1：单号BX-2026-031，报销人张晨，日期2026-03-18，金额1280，类型餐饮，说明团队聚餐，参与人无，发票已上传。
记录2：单号BX-2026-032，报销人李雯，日期2026-03-18，金额86，类型打车，说明客户拜访后返回，出发地浦东软件园，目的地缺失，电子发票。
记录3：单号BX-2026-033，报销人王涛，日期缺失，金额560，类型办公用品，说明打印纸、文件夹，小票模糊。
记录4：单号BX-2026-034，报销人张晨，日期2026-03-18，金额1280，类型餐饮，说明项目沟通晚餐，参与人未写，发票图片。
记录5：单号BX-2026-035，报销人赵敏，日期2026-03-17，金额245，类型打车，说明机场往返，出发地虹桥机场，目的地静安寺，电子发票齐全。"""
    
    result = skill_main(test_input)
    print(result)