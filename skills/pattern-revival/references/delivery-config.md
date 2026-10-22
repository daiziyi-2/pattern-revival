# 可替换单元的数字交付需求

运行 `run_delivery.py --brief <需求.json> --output <新的目录>`。默认实际四瓣，第二案例是[真实八角需求](../assets/briefs/octagon-delivery.json)，可按[四瓣需求](../assets/briefs/quatrefoil-delivery.json)的字段创建本次配置。输入路径相对需求文件解析，支持显式绝对路径；不要仅改名字却沿用旧单元。

| 字段 | 含义与约束 |
|---|---|
| case_id、name、unit_name、features | 当前案例ID、名称及实际识别特征，不作为文化出处证明 |
| deliverables | 可选poster/package/magnet/fabric列表；只生成所列应用，只要求对应配置；空列表仅交付单元和连续。省略时保留完整案例默认值 |
| inputs.unit | 实际静态SVG单元，需带viewBox并符合本地工具输入范围；不能用嵌入PNG替代 |
| inputs.extracted_unit、source_reference | 可选真实提取/整理单元与原型对照；未提供时明确未做照片提取 |
| unit_color_roles | 母版已有HEX→palette角色；预检不存在的颜色映射和错误主纹色，修改颜色属性不改几何 |
| palette | 主纹与背景必填且不同色；模板位置用的朱红/园林青/文字默认沿用主纹，纸面默认背景，可明确指定，不自动借旧案例色值 |
| layout.tile、placements | 完整重复块与实际位置，支持rotate、等比scale、mirror；参数和图形共同决定结果，不能把默认布局自动称为理想连缀 |
| applications.poster、package | width_mm、height_mm、repeat_width_mm，实际毫米画板与印花尺度；尺寸20–2000mm |
| applications.magnet | 单枚宽高；mode默认motif_tiles（完整单元自由摆放），connected_quadrants将完整画面四等分并原位拼回；presentation=flat交接平面稿，product交接摄影候选；输出组合、拆分与单枚稿，不猜测轮廓切割工艺 |
| applications.package.depth_mm | 四面展开概念的深度；未给时假设正面短边的1/4，20–2000mm，depth_assumed随搬移保留；示意展开不等于刀版 |
| colorways | 一至四项，含name、foreground、background（后两者为色板角色）；输出同结构配色 |
| brand_assets、product_references | 明确指定的symbol/foliage SVG、bag/packaging照片，可全部为空，不借旧品牌 |
| poster_use_symbol | 可设false，内部交叉线等关键结构与主题图形冲突时按构图舍去后者 |
| poster_title/subtitle、package_title/subtitle、copy | 真实文案，长文字按可用宽度缩字号；主标题只出现一次 |
| prompt_rules、source_note、culture | 具体提取/保留/线稿要求、人工介入及文化证据状态，无证据不填寓意 |
| prompt_tasks | 可选实际任务ID列表；默认含包装展开的11类交接，缺实际原型或提取单元时跳过提取项；手动请求提取项也必须两者齐全 |
| reference_files | 独立提示词导出时，把逻辑参考名映射到case内实际文件，禁止越出case |

输出需求中的路径改为相对交付目录，搬移后可用该需求再生成新版本。已有母版、旧成果和输入文件保留不覆盖。配置预检只验证支持范围与数据一致性，设计效果仍须看图；模板是一种版式起点，不代表每种纹样或用户参考都应采用相同构图。

交付后可运行`delivery_audit.py --case <成果目录>`重新核对文件、结构、尺寸、参考指纹及已有接缝记录是否仍绑定当前母版。四块磁贴模式有渲染依赖时检查拼回画面与整体母版的像素差；审美、来源、生产与豆包真实输出保持待人工核对。

例如仅做海报和四块还原磁贴，设`deliverables=["poster","magnet"]`，只提供`applications.poster`、`applications.magnet`，磁贴设`mode="connected_quadrants"`、`presentation="flat"`；无需包装文案/尺寸或面料配色。默认提示词也按所选应用裁减；独立`prompt_tasks`用于额外指定交接任务。`repeat`及`sizes`从实际布局与尺寸推导，旧模板残留文字不会覆盖当前参数。
