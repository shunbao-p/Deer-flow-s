#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天气技能使用示例
演示如何集成和使用天气技能
"""

import json
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from skill_main import WeatherSkill
from trigger_detector import WeatherTriggerDetector


class WeatherSkillIntegration:
    """天气技能集成示例"""
    
    def __init__(self):
        self.detector = WeatherTriggerDetector()
        self.skill = WeatherSkill()
    
    def process_user_query(self, user_query: str, mock_search_results: list = None):
        """
        处理用户查询
        
        Args:
            user_query: 用户查询文本
            mock_search_results: 模拟的搜索结果（用于测试）
            
        Returns:
            处理结果字典
        """
        # 步骤1：检测是否触发天气技能
        should_trigger, confidence = self.detector.should_trigger(user_query)
        
        if not should_trigger:
            return {
                "triggered": False,
                "confidence": confidence,
                "message": "查询不匹配天气技能",
                "suggestion": "尝试包含'天气'、'温度'或'weather'等关键词"
            }
        
        print(f"✅ 检测到天气查询 (置信度: {confidence:.2f})")
        
        # 步骤2：提取意图信息
        intent = self.detector.extract_weather_intent(user_query)
        print(f"   意图: {intent}")
        
        # 步骤3：提取城市信息
        city = self.skill.extract_city_from_query(user_query)
        print(f"   城市: {city}")
        
        # 步骤4：构建搜索查询
        search_query = self.skill.build_search_query(city)
        print(f"   搜索查询: {search_query}")
        
        # 步骤5：执行网络搜索（这里使用模拟结果或实际调用web_search）
        if mock_search_results:
            search_results = mock_search_results
            print(f"   使用模拟搜索结果 ({len(search_results)} 条)")
        else:
            # 在实际使用中，这里会调用web_search工具
            # search_results = web_search(search_query)
            search_results = []
            print(f"   注意：实际使用中需要调用web_search('{search_query}')")
        
        # 步骤6：处理结果并生成响应
        result = self.skill.process_query(user_query, search_results)
        
        # 构建完整响应
        response = {
            "triggered": True,
            "confidence": confidence,
            "intent": intent,
            "search_query": search_query,
            "result": result,
            "response_text": result["response"]
        }
        
        return response
    
    def run_examples(self):
        """运行示例查询"""
        print("=== 天气技能集成示例 ===")
        print("演示技能从触发检测到结果生成的全流程\n")
        
        # 模拟搜索结果
        mock_results = [
            {
                "title": "北京天气 - 当前温度25°C",
                "snippet": "北京今天天气晴朗，当前温度25°C，湿度60%，东南风2级"
            },
            {
                "title": "北京天气预报",
                "snippet": "今日最高温度28°C，最低温度20°C，空气质量良好"
            }
        ]
        
        # 测试查询
        test_queries = [
            "今天天气怎么样？",
            "北京天气预报",
            "上海现在温度多少？",
            "weather in New York",
            "明天杭州气温如何？",
            "帮我查一下深圳的天气",
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n{'='*50}")
            print(f"示例 {i}: '{query}'")
            print(f"{'='*50}")
            
            result = self.process_user_query(query, mock_results)
            
            if result["triggered"]:
                print(f"\n📋 结果:")
                print(f"   响应: {result['response_text']}")
                print(f"   详细结果: {json.dumps(result['result'], ensure_ascii=False, indent=2)}")
            else:
                print(f"\n❌ 未触发技能")
                print(f"   原因: {result['message']}")
                print(f"   建议: {result['suggestion']}")
        
        print(f"\n{'='*50}")
        print("示例运行完成！")
    
    def integration_guide(self):
        """提供集成指南"""
        print("\n=== 天气技能集成指南 ===")
        print("\n要集成天气技能到您的应用中，请遵循以下步骤：")
        
        print("\n1. 导入必要的模块:")
        print("""
```python
from trigger_detector import WeatherTriggerDetector
from skill_main import WeatherSkill
```
""")
        
        print("\n2. 初始化检测器和技能:")
        print("""
```python
detector = WeatherTriggerDetector()
skill = WeatherSkill()
```
""")
        
        print("\n3. 在消息处理流程中添加触发检测:")
        print("""
```python
def handle_user_message(user_query):
    # 检测是否触发天气技能
    should_trigger, confidence = detector.should_trigger(user_query)
    
    if should_trigger:
        # 提取城市信息
        city = skill.extract_city_from_query(user_query)
        
        # 构建搜索查询
        search_query = skill.build_search_query(city)
        
        # 调用web_search工具（在实际AI环境中）
        # search_results = await web_search(search_query)
        
        # 处理结果
        result = skill.process_query(user_query, search_results)
        return result["response"]
    
    # 其他技能处理...
    return None
```
""")
        
        print("\n4. 配置技能参数:")
        print("""
技能支持以下配置：
- 默认城市: 修改skill.default_city
- 温度单位偏好: 可扩展支持用户偏好
- 语言检测: 自动检测中英文
""")
        
        print("\n5. 错误处理和降级:")
        print("""
建议添加错误处理：
```python
try:
    result = skill.process_query(user_query, search_results)
    response = result["response"]
except Exception as e:
    # 降级响应
    response = f"抱歉，查询天气时出现错误: {str(e)}"
```
""")


def main():
    """主函数"""
    integration = WeatherSkillIntegration()
    
    # 运行示例
    integration.run_examples()
    
    # 显示集成指南
    integration.integration_guide()


if __name__ == "__main__":
    main()