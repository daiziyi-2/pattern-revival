# 纹样提取与焕活 · Pattern Revival

从原型提取纹样单元，制作连续纹样、配色与线稿，再用于海报、包装和文创。

## 安装地址

技能目录：<https://github.com/daiziyi-2/pattern-revival/tree/main/skills/pattern-revival>

在 Codex 中使用技能安装器，可发送：

```text
请使用 skill-installer 安装这个技能：
https://github.com/daiziyi-2/pattern-revival/tree/main/skills/pattern-revival
```

也可将仓库中的 `skills/pattern-revival` 文件夹复制到目标工具的技能目录。
Codex 的默认用户技能位置为 `~/.codex/skills/pattern-revival`。
仓库当前为私有，安装前需要登录有访问权限的 GitHub 账号。

## 使用示例

```text
使用 $pattern-revival，从这张窗棂照片提取几何单元，排列为四方连续纹样，
沿用参考色板，交付线稿、配色版和一张包装应用概念稿。
```

已有单元或成纹时可直接从对应阶段继续，不必重新提取。只换色或去色时保持结构。

## 文件与能力

- `skills/pattern-revival/SKILL.md`：技能入口和任务路由。
- `references/`：提取、排列、配色、应用、输出控制和跨 AI 交接规则。
- `assets/`：团队对照、可编辑单元、色板、排列配置与实际需求示例。
- `scripts/`：SVG 操作、应用模板、数字交付、提示词导出和验证工具。

图像提取与产品效果需要宿主实际可用的图像/设计工具。本地脚本复用已有路径，
不把照片自动转成可制造文件；概念包装不等于生产刀版。团队资产与规则示范分别标注。

## 本地运行

建议 Python 3.10 或以上。从技能目录执行：

```bash
python -m pip install -r scripts/requirements-render.txt
python scripts/run_case.py --output ./output/example
python scripts/run_delivery.py --brief assets/briefs/octagon-delivery.json --output ./output/octagon
```

仅需矢量结果时添加 `--vector-only`。重新读取 PDF 兼容 AI/PDF 路径时，
额外安装 `scripts/requirements-source.txt` 的依赖，并提供本地原始文件和选择配置；
仓库包含已导出的路径，不包含原始 AI 文档。

验证命令：

```bash
python -m unittest discover -s scripts -p "test_*.py" -v
```

缺少可选渲染依赖或原始设计文件时，对应测试会跳过；以实际输出为准。

## 发布包

[下载技能压缩包](https://github.com/daiziyi-2/pattern-revival/releases/latest/download/pattern-revival.zip)

压缩包解压后顶层目录为 `pattern-revival`，包含技能入口、参考、资产和脚本。
发布副本去除了运行缓存和本机绝对路径；本地工作目录保持不变。
