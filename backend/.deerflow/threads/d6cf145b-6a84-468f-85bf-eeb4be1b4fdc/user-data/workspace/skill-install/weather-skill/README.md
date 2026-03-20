# 天气查询技能

一个智能天气查询技能，使用web_search工具搜索天气信息并提取温度数据。

## 功能特性

- 🎯 **智能触发**: 自动检测包含"天气"、"温度"、"weather"、"temperature"等关键词的查询
- 🌍 **多语言支持**: 支持中文和英文查询
- 🏙️ **城市识别**: 自动从查询中提取城市信息
- 🌡️ **温度提取**: 从搜索结果中智能提取温度信息
- 🔄 **单位转换**: 自动在摄氏度和华氏度之间转换
- 📊 **置信度评分**: 提供触发置信度评估
- 🧪 **完整测试**: 包含单元测试和集成测试

## 技能结构

```
weather-skill/
├── SKILL.md                    # 技能定义文件
├── README.md                   # 使用说明
├── scripts/
│   ├── skill_main.py          # 技能主逻辑
│   ├── trigger_detector.py    # 触发检测器
│   ├── test_weather.py        # 单元测试
│   └── example_usage.py       # 使用示例
├── references/
│   └── (参考文档)
└── assets/
    └── (资源文件)
```

## 快速开始

### 1. 安装依赖

技能需要Python 3.7+，无外部依赖：

```bash
# 进入技能目录
cd weather-skill

# 运行测试
python scripts/test_weather.py

# 运行示例
python scripts/example_usage.py
```

### 2. 基本使用

```python
from scripts.skill_main import WeatherSkill
from scripts.trigger_detector import WeatherTriggerDetector

# 初始化
detector = WeatherTriggerDetector()
skill = WeatherSkill()

# 检测触发
user_query = "北京今天天气怎么样？"
should_trigger, confidence = detector.should_trigger(user_query)

if should_trigger:
    # 提取城市
    city = skill.extract_city_from_query(user_query)
    
    # 构建搜索查询
    search_query = skill.build_search_query(city)
    
    # 调用web_search（在实际AI环境中）
    # search_results = web_search(search_query)
    
    # 处理结果
    result = skill.process_query(user_query, search_results)
    print(result["response"])  # "北京当前温度：25°C (77.0°F)"
```

### 3. 集成到AI代理

要集成到DeerFlow等AI代理平台：

1. **添加触发检测**: 在消息处理流程中加入天气技能触发检测
2. **调用web_search**: 使用平台的web_search工具获取天气信息
3. **处理并返回**: 使用技能处理搜索结果并生成响应

## 技能配置

### 触发关键词

技能会检测以下关键词（中英文）：

- **中文**: 天气, 天气预报, 气温, 温度, 气候, 天气怎么样, 天气如何, °C, °F, 度
- **英文**: weather, temperature, forecast, climate, how's the weather, what's the weather, °C, °F, degrees

### 默认城市

当查询未指定城市时，使用默认城市"本地"。可修改`skill.default_city`属性。

### 置信度阈值

默认触发阈值为0.3（30%置信度）。可调整`should_trigger`方法的判断逻辑。

## 测试用例

技能包含完整的测试套件：

```bash
# 运行所有测试
python scripts/test_weather.py

# 测试触发检测
python scripts/trigger_detector.py
```

### 测试覆盖范围

1. **城市提取测试**: 验证从不同查询中提取城市名的准确性
2. **搜索查询构建**: 测试中英文搜索查询的生成
3. **温度提取**: 验证从搜索结果中提取温度信息
4. **触发检测**: 测试技能触发逻辑
5. **完整流程**: 端到端集成测试

## 扩展开发

### 添加新功能

1. **扩展城市识别**: 修改`skill_main.py`中的`extract_city_from_query`方法
2. **添加新触发词**: 更新`trigger_detector.py`中的关键词列表
3. **增强温度提取**: 改进`extract_temperature_from_results`方法的正则表达式
4. **支持更多天气信息**: 扩展以获取湿度、风速、降水概率等

### 国际化支持

技能已支持中英文，可扩展支持更多语言：

1. 在`trigger_detector.py`中添加新语言的触发词
2. 更新`extract_city_from_query`方法支持新语言
3. 添加对应的测试用例

## 性能优化

- **缓存机制**: 可添加天气结果缓存，减少重复搜索
- **批量处理**: 支持同时查询多个城市的天气
- **异步处理**: 优化网络搜索的并发处理
- **降级策略**: 当主要数据源不可用时使用备用方案

## 故障排除

### 常见问题

1. **技能未触发**
   - 检查查询是否包含天气相关关键词
   - 验证触发检测器的置信度阈值
   - 查看`trigger_detector.py`中的关键词列表

2. **温度提取不准确**
   - 检查搜索结果格式是否匹配预期
   - 验证温度提取正则表达式
   - 考虑添加更多匹配模式

3. **城市识别错误**
   - 检查城市提取逻辑
   - 添加特定城市的别名处理
   - 考虑使用地理位置API增强识别

### 调试模式

技能提供详细的调试输出，可在开发时启用：

```python
# 在skill_main.py中启用调试
skill = WeatherSkill()
skill.debug = True  # 如有调试模式
```

## 贡献指南

欢迎贡献改进！请遵循以下步骤：

1. Fork仓库
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

### 代码规范

- 遵循PEP 8编码规范
- 添加适当的注释和文档
- 为新功能编写测试用例
- 确保所有测试通过

## 许可证

本项目采用MIT许可证。详见LICENSE文件。

## 支持与联系

如有问题或建议，请：

1. 查看[SKILL.md](SKILL.md)获取技能详细说明
2. 检查测试用例了解预期行为
3. 提交Issue报告问题
4. 参与讨论提出改进建议

---

**最后更新**: 2026-03-19  
**版本**: 1.0.0  
**作者**: DeerFlow AI Agent Platform