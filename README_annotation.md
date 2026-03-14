# 心理量表标注助手

用于快速对表现进行心理量表的分数标注，提高标注效率，支持多种项目格式。

## 快速开始

```bash
# 使用默认文件 anotation_example.json
python annotation_tool.py

# 指定输入文件
python annotation_tool.py 你的数据.json

# 指定输出文件（不覆盖原文件）
python annotation_tool.py 数据.json -o 数据_已标注.json
```

## 使用方法

1. 运行程序后，会逐条显示待标注内容
2. **输入格式**：`分数 [置信度]`
   - 例如：`3 4` 表示分数 3、置信度 4
   - 若只输入分数（如 `3`），置信度将使用上一输入或默认值
3. **命令**：
   - 直接回车：跳过当前条，进入下一条
   - `s`：跳过
   - `p`：返回上一条（可修改）
   - `q`：保存并退出
4. 每次有效标注后会自动保存，支持随时退出

## 配置文件

通过 `annotation_config.json` 可自定义字段名和分数范围，以适配不同项目：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| score_range | 分数取值范围 [最小, 最大] | [0, 3] |
| confidence_range | 置信度取值范围 | [1, 3] |
| id_field | ID 字段名 | id |
| response_field | 用户回应字段名 | user_response |
| score_field | 分数字段名 | annotator_score |
| confidence_field | 置信度字段名 | annotator_confidence |

```bash
python annotation_tool.py 数据.json -c 自定义配置.json
```

## 数据格式要求

输入的 JSON 文件应为对象数组，每个对象至少包含：
- 用于显示的内容字段（如 user_response）
- 待填写的分数、置信度字段（初值为 null）

示例结构见 `anotation_example.json`。
