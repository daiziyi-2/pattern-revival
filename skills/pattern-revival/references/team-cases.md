# 团队成稿与真实对照

以下为团队提供的设计过程资料，校准选取对象、整理、排列和应用。图片不证明地理来源或寓意，未附来源凭证的部分待核查；对照截图不算可编辑源文件。

| 案例 | 提取 | 排列 | 文件 |
|---|---|---|---|
| 四瓣形 | 选择窗格镂空，整理双轮廓；不取六角花卉 | 错位、轮廓带和正负形组织，粉紫配色 | [提取](../assets/cases/quatrefoil-extraction.png)、[排列](../assets/cases/quatrefoil-arrangement.png) |
| 回折窗棂 | 选择中央花饰周围直角棂，整理条带 | 整理圆角/通道，纵横组织，红青与黑紫版 | [提取](../assets/cases/meander-extraction.png)、[排列](../assets/cases/meander-arrangement.png) |
| 八角框 | 保留双框，内部整理成交叉和方节点 | 交错连续，双色或单色线稿 | [提取](../assets/cases/octagon-extraction.png)、[排列](../assets/cases/octagon-arrangement.png) |

先看对应两图。截图不证明角度、操作顺序或真实尺寸，需在源文件核对。应用裁切图不能当已经检查的重复块。

## 六套成稿与应用

“凭窗”：四瓣与负形；“临池”：弧段错位；“入园”：环形相交；“穿庭”：回折；“拂竹”：阶梯四出框；“仰檐”：八角与节点。它们是设计主题名，不自动当纹样学名或来源证据。

[成稿总览](../assets/cases/vi-patterns-overview.jpg)。三套有完整对照，另外三套按选定成稿复用，新提取需补来源。

动物主题和几何分层。鹿、鹤、马、麒麟等可复用已有母版；马纹配图与鹿纹照片的对应需核查。系列应用参考黑白建筑照片、鲜明色块、几何纹样、动物图形和中文标题，构图随内容，不固定照抄页面。

[品牌色板](../assets/palettes/zhu-garden.json)暂按 VI 第 5 页 HEX 标注保存。实际源文件、RGB/CMYK 标注和印刷颜色需统一核对。新色板只进入新版本，不覆盖全部系列。

## 工具示范单元

[四瓣规则示范](../assets/units/quatrefoil-rule-demo.svg)、[八角规则示范](../assets/units/octagon-rule-demo.svg)是本技能绘制的可编辑工具示范，不是团队原始路径、原物精确复原或完整成稿复制。忠实成稿使用团队核对的源文件。

## 四瓣形实际源路径与离线复现

本次核对了团队目录中的 PDF 兼容 AI 文件，增加两个真实单元；两者具有同一案例关系，但不是同一几何版本。

| 阶段 | 实际选择 | 打包资产 | 核对状态 |
|---|---|---|---|
| 双轮廓提取 | 纹样提取(1).ai 第2页，绘制路径索引26、27 | [提取单元](../assets/units/quatrefoil-team-extracted.svg)、[选择及指纹](../assets/cases/quatrefoil-extraction-selection.json) | 与原页局部渲染对照；保留有效裁切 |
| 粗描边成纹单元 | 纹样(2).ai 第1页，绘制路径索引269 | [成纹单元](../assets/units/quatrefoil-team-arrangement.svg)、[选择及指纹](../assets/cases/quatrefoil-arrangement-selection.json) | 直接导出原路径；原文件描边宽度14 |
| 新连续版本 | 使用成纹单元，本次均匀化周期124.8×183.4；第二位置偏移62.4、91.7 | [排列配置](../assets/layouts/quatrefoil-team-stagger.json) | 本次定义规则，不追认作者历史操作或精确复制整幅原成纹 |
| 应用 | A3海报、240×80mm平面包装腰封 | [海报模板](../assets/layouts/poster-quatrefoil.json)、[腰封模板](../assets/layouts/sleeve-quatrefoil.json) | 毫米尺寸为概念假设；非生产文件 |

索引从0开始且仅适用于选择配置中的源文件SHA256。源文件改动后必须重新核对，不能沿用旧索引。SVG保存实际RGB路径与必要裁切，未保留Illustrator专有图层、CMYK数据或操作历史。地理来源、照片使用条件和文化寓意仍待核查。

离线运行 `scripts/run_case.py` 不需要原AI文件、PyMuPDF、网络或生成接口，使用包内实际路径及导出凭证。若要重新从原文件导出，则使用 `export_unit.py` 与对应选择配置。示范单元仍保留，与真实单元分开。

## 八角实际单元与第二个数字交付案例

已从`纹样(2).ai`第1页绘制路径73–80导出[真实八角单元](../assets/units/octagon-team-arrangement.svg)，包含双框、四个方节点与交叉线，选择凭证见[指纹与索引](../assets/cases/octagon-team-selection.json)。这是团队既有成纹路径，不是本次照片自动提取。

[八角需求](../assets/briefs/octagon-delivery.json)使用不同配色、A4海报与200×136mm包装，另定义165×175直排周期，保留间隙；不声称复现原截图的交错连缀。运行`run_delivery.py --brief assets/briefs/octagon-delivery.json`可完成连续、线稿、应用与实填提示词。

回折二维连缀、八角原截图交错连接的精确复现、未知照片的新提取仍待完成。跨案例脚本验证不能代替豆包实际对话测试或文化/生产验收。
