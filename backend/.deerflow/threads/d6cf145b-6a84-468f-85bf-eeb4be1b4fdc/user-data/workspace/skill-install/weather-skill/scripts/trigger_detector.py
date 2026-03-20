#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天气技能触发检测器
检测用户查询是否应该触发天气技能
"""

import re
from typing import Dict, List, Tuple, Optional


class WeatherTriggerDetector:
    """天气技能触发检测器"""
    
    def __init__(self):
        # 定义触发关键词（中文）
        self.chinese_triggers = [
            "天气", "天气预报", "气温", "温度", "气候",
            "天气怎么样", "天气如何", "天气情况",
            "今天天气", "明天天气", "本周天气",
            "摄氏度", "华氏度", "°C", "°F", "度"
        ]
        
        # 定义触发关键词（英文）
        self.english_triggers = [
            "weather", "temperature", "forecast", "climate",
            "weather today", "weather tomorrow", "weather forecast",
            "how's the weather", "what's the weather",
            "°C", "°F", "degrees", "Celsius", "Fahrenheit"
        ]
        
        # 构建正则表达式模式
        self.patterns = self._build_patterns()
    
    def _build_patterns(self) -> List[re.Pattern]:
        """构建触发检测的正则表达式模式"""
        patterns = []
        
        # 中文模式
        for trigger in self.chinese_triggers:
            pattern = re.compile(f'.*{re.escape(trigger)}.*', re.IGNORECASE)
            patterns.append(pattern)
        
        # 英文模式
        for trigger in self.english_triggers:
            pattern = re.compile(f'\\b{re.escape(trigger)}\\b', re.IGNORECASE)
            patterns.append(pattern)
        
        # 通用天气相关模式
        weather_patterns = [
            r'.*(天气|weather).*',  # 包含"天气"或"weather"
            r'.*(温度|temperature).*',  # 包含"温度"或"temperature"
            r'.*(forecast|预报).*',  # 包含"forecast"或"预报"
            r'.*°[CF].*',  # 包含温度单位
            r'.*\d+\s*(度|degrees).*',  # 包含数字+度
        ]
        
        for pattern_str in weather_patterns:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            patterns.append(pattern)
        
        return patterns
    
    def should_trigger(self, user_input: str) -> Tuple[bool, float]:
        """
        检测是否应该触发天气技能
        
        Args:
            user_input: 用户输入文本
            
        Returns:
            (是否触发, 置信度分数)
        """
        if not user_input or len(user_input.strip()) < 2:
            return False, 0.0
        
        input_lower = user_input.lower()
        input_text = user_input
        
        # 计算匹配分数
        match_score = 0.0
        
        # 检查确切关键词匹配
        exact_matches = 0
        
        # 中文关键词检查
        for trigger in self.chinese_triggers:
            if trigger in input_text:
                exact_matches += 1
                match_score += 1.0
        
        # 英文关键词检查
        for trigger in self.english_triggers:
            if re.search(rf'\b{re.escape(trigger)}\b', input_lower):
                exact_matches += 1
                match_score += 1.0
        
        # 正则表达式模式匹配
        pattern_matches = 0
        for pattern in self.patterns:
            if pattern.search(input_text) or pattern.search(input_lower):
                pattern_matches += 1
                match_score += 0.5
        
        # 计算置信度分数
        confidence = min(1.0, match_score / 5.0)  # 归一化到0-1
        
        # 判断是否触发
        should_trigger = exact_matches > 0 or pattern_matches >= 2
        
        # 如果置信度超过阈值，则触发
        if confidence > 0.3:
            should_trigger = True
        
        return should_trigger, confidence
    
    def extract_weather_intent(self, user_input: str) -> Dict[str, any]:
        """
        提取天气查询的意图信息
        
        Args:
            user_input: 用户输入文本
            
        Returns:
            意图信息字典
        """
        intent = {
            "type": "weather_query",
            "has_location": False,
            "location": None,
            "time_frame": "current",  # current, today, tomorrow, week
            "detail_level": "temperature",  # temperature, full, brief
            "language": self.detect_language(user_input)
        }
        
        # 检测语言
        intent["language"] = self.detect_language(user_input)
        
        # 检测时间范围
        time_keywords = {
            "current": ["现在", "当前", "此刻", "now", "current"],
            "today": ["今天", "今日", "today", "this day"],
            "tomorrow": ["明天", "明日", "tomorrow"],
            "week": ["本周", "这周", "week", "this week"]
        }
        
        for time_frame, keywords in time_keywords.items():
            for keyword in keywords:
                if keyword in user_input:
                    intent["time_frame"] = time_frame
                    break
        
        # 检测详细程度
        if any(word in user_input for word in ["详细", "全面", "详细天气", "detailed", "full"]):
            intent["detail_level"] = "full"
        elif any(word in user_input for word in ["温度", "气温", "温度多少", "temperature"]):
            intent["detail_level"] = "temperature"
        
        return intent
    
    def detect_language(self, text: str) -> str:
        """检测输入文本的语言"""
        # 简单检测：如果有中文字符，则为中文
        if any('\u4e00' <= char <= '\u9fff' for char in text):
            return "zh"
        # 如果有英文字母，则为英文
        elif any('a' <= char.lower() <= 'z' for char in text):
            return "en"
        else:
            return "unknown"
    
    def get_trigger_examples(self) -> List[str]:
        """获取触发示例"""
        examples = []
        
        # 中文示例
        chinese_examples = [
            "今天天气怎么样？",
            "北京天气预报",
            "上海现在温度多少？",
            "天气如何？",
            "告诉我本地天气",
            "气温多少度？",
            "明天天气",
            "本周天气情况",
        ]
        
        # 英文示例
        english_examples = [
            "What's the weather like today?",
            "Weather in New York",
            "How's the temperature now?",
            "Weather forecast for tomorrow",
            "Current weather",
            "Tell me the temperature",
            "Is it going to rain today?",
            "Weather this week",
        ]
        
        examples.extend(chinese_examples)
        examples.extend(english_examples)
        
        return examples
    
    def get_non_trigger_examples(self) -> List[str]:
        """获取不触发示例"""
        non_examples = [
            "今天吃什么？",
            "帮我写一封邮件",
            "解释一下人工智能",
            "计算器功能",
            "翻译这句话",
            "创建一张图片",
            "播放音乐",
            "设置提醒",
            "什么是机器学习？",
            "如何学习编程？",
        ]
        
        return non_examples


def test_detector():
    """测试触发检测器"""
    detector = WeatherTriggerDetector()
    
    print("=== 天气技能触发检测器测试 ===")
    
    # 测试触发示例
    print("\n应该触发的查询:")
    trigger_examples = detector.get_trigger_examples()
    for example in trigger_examples[:5]:  # 测试前5个
        should_trigger, confidence = detector.should_trigger(example)
        intent = detector.extract_weather_intent(example)
        print(f"查询: {example}")
        print(f"  触发: {should_trigger} (置信度: {confidence:.2f})")
        print(f"  意图: {intent}")
    
    # 测试不触发示例
    print("\n不应该触发的查询:")
    non_trigger_examples = detector.get_non_trigger_examples()
    for example in non_trigger_examples[:5]:  # 测试前5个
        should_trigger, confidence = detector.should_trigger(example)
        print(f"查询: {example}")
        print(f"  触发: {should_trigger} (置信度: {confidence:.2f})")


if __name__ == "__main__":
    test_detector()