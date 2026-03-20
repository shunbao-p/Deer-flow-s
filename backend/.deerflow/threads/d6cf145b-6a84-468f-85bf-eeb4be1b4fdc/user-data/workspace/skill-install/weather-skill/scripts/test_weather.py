#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天气技能测试脚本
模拟技能触发和web_search调用
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from skill_main import WeatherSkill


class WeatherSkillTester:
    """天气技能测试器"""
    
    def __init__(self):
        self.skill = WeatherSkill()
        self.test_results = []
    
    def test_city_extraction(self):
        """测试城市提取功能"""
        print("\n=== 城市提取测试 ===")
        
        test_cases = [
            ("今天天气怎么样？", "本地"),
            ("北京天气预报", "北京"),
            ("上海现在温度多少？", "上海"),
            ("weather in New York", "New York"),
            ("杭州气温", "杭州"),
            ("深圳天气如何？", "深圳"),
            ("温度多少？", "本地"),
            ("告诉我纽约的天气", "纽约"),
        ]
        
        for query, expected in test_cases:
            actual = self.skill.extract_city_from_query(query)
            passed = actual == expected
            self.test_results.append({
                "test": "city_extraction",
                "query": query,
                "expected": expected,
                "actual": actual,
                "passed": passed
            })
            print(f"查询: {query}")
            print(f"  预期: {expected}")
            print(f"  实际: {actual}")
            print(f"  结果: {'✓' if passed else '✗'}")
    
    def test_search_query_building(self):
        """测试搜索查询构建"""
        print("\n=== 搜索查询构建测试 ===")
        
        test_cases = [
            ("本地", "current weather"),
            ("北京", "北京 当前天气 温度"),
            ("Shanghai", "weather in Shanghai current temperature"),
            ("New York", "weather in New York current temperature"),
            ("东京", "东京 当前天气 温度"),
        ]
        
        for city, expected in test_cases:
            actual = self.skill.build_search_query(city)
            self.test_results.append({
                "test": "search_query",
                "city": city,
                "expected": expected,
                "actual": actual,
                "passed": actual == expected
            })
            print(f"城市: {city}")
            print(f"  预期: {expected}")
            print(f"  实际: {actual}")
            print(f"  结果: {'✓' if actual == expected else '✗'}")
    
    def test_temperature_extraction(self):
        """测试温度提取（使用模拟搜索结果）"""
        print("\n=== 温度提取测试 ===")
        
        # 模拟搜索结果
        mock_results_celsius = [
            {
                "title": "北京天气 - 当前温度25°C",
                "snippet": "北京今天天气晴朗，当前温度25°C，湿度60%"
            },
            {
                "title": "北京天气预报",
                "snippet": "今日最高温度28°C，最低温度20°C"
            }
        ]
        
        mock_results_fahrenheit = [
            {
                "title": "New York Weather - 77°F",
                "snippet": "Currently 77°F in New York, partly cloudy"
            }
        ]
        
        mock_results_mixed = [
            {
                "title": "上海天气",
                "snippet": "当前气温22度，天气多云"
            }
        ]
        
        test_cases = [
            ("摄氏度测试", mock_results_celsius, "25°C (77.0°F)"),
            ("华氏度测试", mock_results_fahrenheit, "25.0°C (77°F)"),
            ("混合测试", mock_results_mixed, "22°C"),
        ]
        
        for name, results, expected in test_cases:
            actual = self.skill.extract_temperature_from_results(results)
            passed = actual == expected
            
            self.test_results.append({
                "test": "temperature_extraction",
                "name": name,
                "expected": expected,
                "actual": actual,
                "passed": passed
            })
            
            print(f"测试: {name}")
            print(f"  预期: {expected}")
            print(f"  实际: {actual}")
            print(f"  结果: {'✓' if passed else '✗'}")
    
    def test_full_processing(self):
        """测试完整处理流程"""
        print("\n=== 完整流程测试 ===")
        
        mock_results = [
            {
                "title": "北京天气 - 当前温度25°C",
                "snippet": "北京今天天气晴朗，当前温度25°C"
            }
        ]
        
        test_queries = [
            ("北京天气怎么样？", "北京当前温度：25°C (77.0°F)"),
            ("上海温度", "上海当前温度：25°C (77.0°F)"),  # 注意：实际会使用相同模拟结果
        ]
        
        for query, expected_response in test_queries:
            # 为简单起见，我们使用相同的模拟结果
            result = self.skill.process_query(query, mock_results)
            actual_response = result["response"]
            
            self.test_results.append({
                "test": "full_processing",
                "query": query,
                "expected": expected_response,
                "actual": actual_response,
                "passed": "北京" in actual_response  # 简单检查
            })
            
            print(f"查询: {query}")
            print(f"  响应: {actual_response}")
    
    def run_all_tests(self):
        """运行所有测试"""
        print("开始天气技能测试...")
        
        self.test_city_extraction()
        self.test_search_query_building()
        self.test_temperature_extraction()
        self.test_full_processing()
        
        # 统计结果
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r["passed"])
        
        print(f"\n=== 测试总结 ===")
        print(f"总测试数: {total}")
        print(f"通过数: {passed}")
        print(f"失败数: {total - passed}")
        print(f"通过率: {passed/total*100:.1f}%")
        
        # 显示失败详情
        failures = [r for r in self.test_results if not r["passed"]]
        if failures:
            print("\n失败的测试:")
            for failure in failures:
                print(f"  - {failure['test']}: {failure.get('query', failure.get('name', 'N/A'))}")
                print(f"    预期: {failure.get('expected', 'N/A')}")
                print(f"    实际: {failure.get('actual', 'N/A')}")
        
        return passed == total


def main():
    """主测试函数"""
    tester = WeatherSkillTester()
    all_passed = tester.run_all_tests()
    
    if all_passed:
        print("\n✅ 所有测试通过！技能功能正常。")
        return 0
    else:
        print("\n❌ 部分测试失败，请检查技能实现。")
        return 1


if __name__ == "__main__":
    sys.exit(main())