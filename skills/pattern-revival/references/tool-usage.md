# 可执行 SVG 工具

脚本位于 scripts/pattern_tools.py，基础命令仅依赖 Python 3.9+ 标准库；用当前环境实际可用的 Python，不假定特定机器路径。以下从技能目录运行，跨环境请使用实际绝对路径。默认拒绝覆盖源文件和已有输出；明确要覆盖时使用 --overwrite。

## 输入范围

接受带 SVG 命名空间与 viewBox 的静态 path/rect/circle/ellipse/line/polyline/polygon，以及组、内部 use、clipPath 和 pattern。颜色用 HEX，可使用 none、inherit、currentColor；内联样式优先于属性。拒绝位图、文本、外部引用、脚本、样式表/class、渐变、滤镜和遮罩等，避免误标可编辑能力。先在矢量软件整理不支持的输入；inspect 可报告问题。

## 排列配置

先用实际单元。`quatrefoil-team-*` 是本次从团队文件读取的路径，`*-rule-demo` 是规则示范；见团队案例的版本关系。配置见 assets/layouts。unit 相对配置文件解析；tile 为完整矩形周期；placements 每项支持 x、y、rotate、等比 scale、mirror（none/x/y/xy）。x/y 是归一化单元外框左上位置，旋转围绕缩放后外框中心。视框为非零起点时自动归一化。脚本按横纵周期复制图形，由视口裁切一次；平铺和应用共用完整背景，减少分块背景抗锯齿细线。设计师仍须决定正确单元、连接和共享边。

    python scripts/pattern_tools.py compose --config assets/layouts/quatrefoil-stagger.json --output 成果/四瓣-tile-v1.svg
    python scripts/pattern_tools.py preview --input 成果/四瓣-tile-v1.svg --cols 3 --rows 3 --output 成果/四瓣-平铺-v1.svg
    python scripts/pattern_tools.py preview --input 成果/四瓣-tile-v1.svg --edges --output 成果/四瓣-边界-v1.svg

preview 默认 3×3，支持 1–20 行/列；--edges 加边界虚线，只用于检查副本。

## 换色与线稿

    python scripts/pattern_tools.py paint --input 成果/四瓣-tile-v1.svg --map "#E978D1=#22C9B8" --map "#7B42DD=#E84A27" --output 成果/四瓣-改色-v1.svg
    python scripts/pattern_tools.py lineart --input 成果/四瓣-tile-v1.svg --stroke-width 1.5 --output 成果/四瓣-线稿-v1.svg
    python scripts/pattern_tools.py compare --before 成果/四瓣-tile-v1.svg --after 成果/四瓣-线稿-v1.svg

paint 对填充、描边及 color 的指定 HEX 改色，未命中则报错。lineart 去填充、加指定轮廓描边，默认黑线白底；--background none 去本工具标记的背景，不做自动背景分割；--ink 指定线色。不指定线宽时保留已有描边宽度。双轮廓保留双轮廓，不自动变中心骨架。其他未标记的白色矩形仍视为图形，按轮廓处理。

几何比较排除颜色、描边属性和 data-role=background 的背景，保留路径、坐标、变换、层级和裁切。一致不等于视觉、印刷和接缝通过。lineart 与 paint 自动检查后才写文件；各 SVG 操作产生 *.record.json，人工检查项默认未检查。

## 检查与渲染

    python scripts/pattern_tools.py inspect --input 成果/四瓣-tile-v1.svg
    python scripts/pattern_tools.py render --input 成果/四瓣-平铺-v1.svg --width 1200 --output 成果/四瓣-平铺-v1.png

render 是矢量预览导出，依赖可选 resvg-py；需要时使用 scripts/requirements-render.txt 安装到实际运行环境。依赖不可用时用宿主 SVG/设计工具导出，基础命令仍可执行，不把 PNG 当新矢量。渲染后实际看图检查；静态 inspect 不自动验证接缝、路径拓扑或文化来源。

## 真实路径重新导出

可选依赖在 `scripts/requirements-source.txt`。仅接受已核对页码、路径索引、源文件SHA256的选择配置；在源文件修改后拒绝盲目沿用索引。支持曲线、线段、矩形和四边形，保留实际起作用的裁切；透明混合或不支持路径需在设计软件整理。

    python scripts/export_unit.py --source "<团队文件目录>/纹样提取(1).ai" --selection assets/cases/quatrefoil-extraction-selection.json --output "<成果目录>/提取单元.svg"

这是读取团队既有路径，不是照片自动提取。导出的RGB颜色不能替代CMYK定稿。原始AI文件保持不变。

## 接缝像素检查

    python scripts/pattern_tools.py check-seams --input "<成果目录>/重复块.svg" --config assets/layouts/quatrefoil-team-stagger.json --output "<成果目录>/接缝.json" --diagnostics

需要resvg-py和Pillow。配置必须引用同一结构和颜色版本。比较裁切后的3×3与同配置在大画布直接绘制的结果，检查两条横缝、两条竖缝及四个交点。默认每块横向512像素；每个窗口允许通道差大于32的像素比例不超过0.5%，报告保留实际差值与容差。不是像素零差或制造验收证明，不判断图形是否构成理想连缀。`--diagnostics`另存平铺、参照和差异PNG。

依赖缺失时不得写通过，继续交付边界SVG供人工检查。出现需修正时看参照与差异图，分清配置不对应、实际断线和栅格化问题，不通过调整容差掩盖设计错误。

## 有尺寸的应用与完整案例

    python scripts/apply_pattern.py --input "<成果目录>/重复块.svg" --template assets/layouts/poster-quatrefoil.json --output "<成果目录>/海报.svg" --render
    python scripts/run_case.py --output "<新的成果目录>"
    python scripts/run_case.py --output "<新的成果目录>" --vector-only

案例命令生成来源卡、实际提取和成纹单元、配置、彩色重复块、3×3与边界图、线稿、A3海报及包装腰封概念、过程报告。它复用团队人工提取，不调用生成服务。输出目录必须为空，应用源文件含真实路径与可编辑文字。母版不随应用覆盖；换色与线稿保持同一几何签名。

应用SVG含text，超出pattern_tools的纹样输入子集：使用apply_pattern自己的 `--render`，不把海报当作下次排列的单元。预览可用 `--font <实际字体文件>` 指定比赛设备字体；不复制或自动分发系统字体。包装模板仅为平面展开概念，不包含核对刀版、生产出血或实物效果图。

`run_case`默认在依赖可用时输出PNG及像素检查；`--vector-only`强制跳过渲染，接缝记未检查。过程记录保留真实测时范围，不换算成任意照片的五分钟承诺。

命令成功返回0，校验失败返回2；禁止输入输出同文件，`--overwrite`仅用于已生成副本。测试入口：`python -m unittest discover -s scripts -p "test_*.py" -v`。测试覆盖受限编辑、周期包裹、断线/跳色反例、本地矢量链和应用尺寸；实际源文件在环境可用时另测源稿与导出像素对照，不需要生成API。

## 完整数字交付与跨AI提示词

    python scripts/run_delivery.py --output "<新的完整交付目录>" --font "<实际中文字体文件>"
    python scripts/run_delivery.py --output "<新的完整交付目录>" --vector-only
    python scripts/run_delivery.py --brief assets/briefs/octagon-delivery.json --output "<新的八角目录>"
    python scripts/run_delivery.py --brief "<本次实际需求.json>" --output "<新的定制目录>"
    python scripts/export_prompts.py --case "<已有成果目录>" --output "<新的提示词包目录>"
    python scripts/export_prompts.py --case "<已有成果目录>" --output "<新的局部提示词目录>" --only 09-仅换色 10-去色线稿

`run_delivery`根据实际需求指定的静态SVG准备基础链，生成品牌海报、包装正面、一至四种面料配色、四枚独立底板磁贴与组合、文化基因卡、SOP及实填提示词。单元来源、色值与尺寸在写入前核对；改色保持几何。没有提取源稿时提供成纹去色参照并明确身份，不冒充照片提取；已有单元而无原型时不导出提取任务。渲染可用时生成PNG，否则提示词明确需转PNG。它不调用图像生成，不把平面稿列为摄影样机。

提示词包包含完整中文TXT、`设计需求.json`、`提示词清单.json`和指纹命名的参考副本，可整体搬移。独立导出优先读取case内的实际需求；显式覆盖若案例、形态特征、色板、周期或尺寸不匹配则拒绝。参考只在case内寻找；旧命名可用需求的reference_files显式映射。不从技能包补入另一案例。未附成稿时标明探索/待补图；可选载体缺失时正文走明确的概念描述，不假装看过照片。

交付目录的需求改为相对本目录引用母版、来源及品牌素材，可以搬移后重新运行；提示词子目录仅含生图交接材料，不含整套可重跑源稿。字段见[需求配置](delivery-config.md)，聊天环境见[豆包与其他agent入口](chat-handoff.md)。
