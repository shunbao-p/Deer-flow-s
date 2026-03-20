#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天气技能主脚本
使用web_search工具查询天气信息
"""

import re
import json
from typing import Dict, List, Optional, Tuple


class WeatherSkill:
    """天气查询技能"""
    
    def __init__(self):
        """初始化技能"""
        self.default_city = "本地"
        
    def extract_city_from_query(self, query: str) -> str:
        """
        从用户查询中提取城市信息
        
        Args:
            query: 用户查询文本
            
        Returns:
            提取的城市名，如果未找到则返回默认值
        """
        # 排除的时间词和常见词
        excluded_terms = ["今天", "明天", "后天", "现在", "当前", "本地", "我", "你", "他", "她", 
                         "它", "这个", "那个", "这里", "那里", "哪里", "如何", "怎么样", "多少",
                         "什么", "哪个", "哪个城市", "告诉我", "请告诉", "查询", "查一下", "看看",
                         "的", "了", "呢", "吗", "吧", "啊"]
        
        # 中文城市列表（常见），包括纽约等国际城市
        chinese_cities = ["北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉", "西安", 
                         "重庆", "天津", "苏州", "郑州", "长沙", "青岛", "大连", "厦门", "福州",
                         "宁波", "无锡", "合肥", "南昌", "昆明", "贵阳", "南宁", "海口", "石家庄",
                         "太原", "哈尔滨", "长春", "沈阳", "兰州", "西宁", "银川", "乌鲁木齐", "拉萨",
                         "香港", "澳门", "台北", "高雄", "台中", "台南", "纽约", "伦敦", "巴黎", 
                         "东京", "悉尼", "新加坡", "首尔", "柏林", "莫斯科", "洛杉矶", "芝加哥"]
        
        # 先检查是否包含已知城市
        for city in chinese_cities:
            if city in query:
                return city
        
        # 英文城市名检测
        english_city_pattern = r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*'
        english_matches = re.findall(english_city_pattern, query)
        
        if english_matches:
            common_english_exclusions = ['Weather', 'Temperature', 'Forecast', 'Current', 
                                       'Today', 'Tomorrow', 'Now', 'Local', 'City', 'How']
            for match in english_matches:
                if (len(match) > 2 and 
                    match not in common_english_exclusions and
                    match.lower() not in ['weather', 'temperature', 'forecast', 'current',
                                         'today', 'tomorrow', 'now', 'local', 'city', 'how']):
                    return match
        
        # 尝试从常见模式中提取
        patterns = [
            r'(?:在|于)?([^的]+?)(?:的)?天气',  # 在北京的天气，非贪婪匹配
            r'天气(?:在|于)?([^的]+)',  # 天气在北京
            r'([^的]+?)(?:天气|天气预报|温度|气温|气候)',  # 北京天气，非贪婪
            r'(?:查询|查一下|看看)?([^的]+?)(?:的)?天气',  # 查询北京天气
            r'(?:告诉我|请告诉|查询|查一下|看看)?([^的]+?)(?:的)?天气',  # 告诉我北京天气
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, query)
            if matches:
                for match in matches:
                    # 清理匹配结果：移除空格和常见词
                    match = match.strip()
                    
                    # 如果匹配包含排除词，尝试提取城市部分
                    if any(excl in match for excl in excluded_terms):
                        # 尝试从匹配中移除排除词
                        for excl in excluded_terms:
                            match = match.replace(excl, '')
                        match = match.strip()
                    
                    # 检查匹配是否有效
                    if (match and 
                        match not in excluded_terms and 
                        not any(excl in match for excl in excluded_terms) and
                        len(match) >= 2):
                        # 检查是否包含时间词
                        time_indicators = ["今天", "明天", "后天", "现在", "当前"]
                        if not any(indicator in match for indicator in time_indicators):
                            return match
        
        return self.default_city
    
    def build_search_query(self, city: str) -> str:
        """
        构建天气搜索查询
        
        Args:
            city: 城市名
            
        Returns:
            优化的搜索查询字符串
        """
        if city == self.default_city or not city:
            return "current weather"
        else:
            # 针对中文城市名使用中文搜索
            if any('\u4e00' <= char <= '\u9fff' for char in city):
                return f"{city} 当前天气 温度"
            else:
                return f"weather in {city} current temperature"
    
    def extract_temperature_from_results(self, search_results: List[Dict]) -> Optional[str]:
        """
        从搜索结果中提取温度信息
        
        Args:
            search_results: web_search返回的结果列表
            
        Returns:
            提取的温度字符串，如果未找到则返回None
        """
        if not search_results:
            return None
        
        # 从多个结果中查找温度信息
        temperature_patterns = [
            r'(\d+)\s*°\s*([CF])',  # 25°C 或 77°F，捕获数字和单位
            r'(\d+)\s*度',  # 25度
            r'temperature[:\s]*(\d+)\s*([CF])?',  # temperature: 25C 或 temperature: 25
            r'(\d+)\s*摄氏度',
            r'(\d+)\s*华氏度',
            r'(\d+)\s*C\b',  # 25C
            r'(\d+)\s*F\b',  # 77F
        ]
        
        all_text = " ".join([result.get('snippet', '') + " " + result.get('title', '') 
                           for result in search_results])
        
        # 优先查找带单位的温度
        for pattern in temperature_patterns:
            matches = re.finditer(pattern, all_text, re.IGNORECASE)
            for match in matches:
                groups = match.groups()
                if len(groups) >= 1:
                    temp = groups[0]
                    unit = None
                    
                    # 确定单位
                    if len(groups) >= 2 and groups[1]:
                        unit_char = groups[1].upper()
                        if unit_char == 'C':
                            unit = '°C'
                        elif unit_char == 'F':
                            unit = '°F'
                    else:
                        # 从上下文推断单位
                        if '°C' in all_text or '摄氏度' in all_text or 'C\b' in all_text:
                            unit = '°C'
                        elif '°F' in all_text or '华氏度' in all_text or 'F\b' in all_text:
                            unit = '°F'
                        else:
                            # 默认为摄氏度
                            unit = '°C'
                    
                    # 执行温度转换
                    try:
                        temp_num = float(temp)
                        if unit == '°C':
                            temp_f = temp_num * 9/5 + 32
                            return f"{temp_num}{unit} ({temp_f:.1f}°F)"
                        elif unit == '°F':
                            temp_c = (temp_num - 32) * 5/9
                            return f"{temp_c:.1f}°C ({temp_num}{unit})"
                        else:
                            return f"{temp_num}{unit}"
                    except ValueError:
                        return f"{temp}{unit}"
        
        return None
    
    def process_query(self, user_query: str, search_results: List[Dict]) -> Dict:
        """
        处理用户查询并返回天气信息
        
        Args:
            user_query: 用户查询文本
            search_results: web_search返回的结果列表
            
        Returns:
            包含天气信息的字典
        """
        # 提取城市信息
        city = self.extract_city_from_query(user_query)
        
        # 提取温度信息
        temperature = self.extract_temperature_from_results(search_results)
        
        # 构建响应
        if temperature:
            response_text = f"{city}当前温度：{temperature}"
        else:
            response_text = f"未找到{city}的温度信息，请尝试更具体的查询。"
        
        return {
            "city": city,
            "temperature": temperature,
            "response": response_text,
            "query": user_query
        }
    
    def generate_test_queries(self) -> List[str]:
        """
        生成测试查询
        
        Returns:
            测试查询列表
        """
        return [
            "今天天气怎么样？",
            "北京天气预报",
            "上海现在温度多少？",
            "weather in New York",
            "本地天气",
            "杭州气温",
            "深圳天气如何？",
            "温度多少？",
        ]


def main():
    """主函数，用于测试"""
    skill = WeatherSkill()
    
    print("=== 天气技能测试 ===")
    print("\n测试查询提取：")
    
    test_queries = skill.generate_test_queries()
    for query in test_queries:
        city = skill.extract_city_from_query(query)
        search_q = skill.build_search_query(city)
        print(f"查询: {query}")
        print(f"  提取城市: {city}")
        print(f"  搜索查询: {search_q}")
        print()


if __name__ == "__main__":
    main()