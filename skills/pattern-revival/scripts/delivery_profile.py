"""通用交付需求读取与预检；配置相对需求文件解析。"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import pattern_tools as t

SKILL = Path(__file__).resolve().parents[1]
DEFAULT = SKILL/'assets/briefs/quatrefoil-delivery.json'


def read(path=None):
    path = Path(path).resolve() if path else DEFAULT
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    explicit_scope = 'deliverables' in data
    data.setdefault('deliverables', ['poster','package','magnet','fabric'])
    if not isinstance(data['deliverables'], list) or any(v not in ('poster','package','magnet','fabric') for v in data['deliverables']):
        raise ValueError('deliverables仅支持poster/package/magnet/fabric；空列表表示只交付单元与连续')
    required=['name','unit_name']
    if 'poster' in data['deliverables']:required+=['brand','poster_title','poster_subtitle']
    if 'package' in data['deliverables']:required+=['brand','package_title','package_subtitle']
    for key in required:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError('需求缺少非空文字：'+key)
    if not isinstance(data.get('features'), list) or not data['features'] or any(not isinstance(v, str) for v in data['features']):
        raise ValueError('features需列出真实母版的识别特征')
    palette=data['palette']
    for role,fallback in [('朱红','轮廓带'),('园林青','轮廓带'),('纸面','负形与背景'),('文字','轮廓带')]:
        palette.setdefault(role,palette[fallback])
    for role in ['轮廓带', '负形与背景', '朱红', '园林青', '纸面', '文字']:
        data['palette'][role] = t.color(data['palette'][role])
    if data['palette']['轮廓带'] == data['palette']['负形与背景']:
        raise ValueError('主纹与背景不能同色，否则单元不可见')
    if data.get('layout') and data.get('applications'):
        describe(data, data['layout'])
    if not data.get('prompt_tasks'):
        jobs=json.loads((SKILL/'assets/prompts/deliverables.json').read_text(encoding='utf-8'))
        scope_jobs={'poster':['04-品牌海报'],'package':['05-包装正面','11-包装展开'],
                    'magnet':['07-模块磁贴'],'fabric':['06-布包效果']}
        allowed={'02-彩色单元','03-连续纹样','09-仅换色','10-去色线稿'}
        if explicit_scope:
            for scope in data['deliverables']:allowed.update(scope_jobs[scope])
        else:
            allowed.update(j['id'] for j in jobs)
        if not (data.get('inputs',{}).get('source_reference') and data.get('inputs',{}).get('extracted_unit')):
            allowed.discard('01-提取线稿')
        data['prompt_tasks']=[j['id'] for j in jobs if j['id'] in allowed]
    return path, data


def resolve(path, value):
    result = (path.parent/value).resolve()
    if not result.is_file():
        raise ValueError('需求引用文件不存在：'+str(result))
    return result


def validate(path=None):
    path, b = read(path)
    inputs = b['inputs']
    unit_path = resolve(path, inputs['unit'])
    unit = t.read_svg(unit_path)
    extracted_path = resolve(path, inputs['extracted_unit']) if inputs.get('extracted_unit') else None
    if extracted_path:
        t.read_svg(extracted_path)
    source = resolve(path, inputs['source_reference']) if inputs.get('source_reference') else None
    color_map = {t.color(k): b['palette'][role] for k, role in b.get('unit_color_roles', {}).items()}
    available = set()
    for el in unit.iter():
        for key in ('fill', 'stroke', 'color'):
            value = t.style(el).get(key, el.get(key, ''))
            if value.startswith('#'):
                available.add(t.color(value))
    if color_map.keys()-available:
        raise ValueError('改色映射含母版中不存在的颜色：'+','.join(sorted(color_map.keys()-available)))
    after_colors = {color_map.get(c,c) for c in available}
    if b['palette']['轮廓带'] not in after_colors:
        raise ValueError('声明的主纹颜色未出现在母版或改色结果中，请补正确的颜色角色映射')
    layout = copy.deepcopy(b['layout'])
    for key in ('width', 'height'):
        layout['tile'][key] = t.number(layout['tile'][key], '重复块'+key, True)
    if not isinstance(layout.get('placements'), list) or not layout['placements']:
        raise ValueError('需要至少一个实际排列位置')
    for placement in layout['placements']:
        for key in ('x', 'y'):
            placement[key] = t.number(placement[key], '排列'+key)
        for key in ('rotate', 'scale'):
            if key in placement:
                placement[key] = t.number(placement[key], key, key=='scale')
        if placement.get('mirror', 'none') not in ('none', 'x', 'y', 'xy'):
            raise ValueError('镜像仅支持none/x/y/xy')
    for name in (v for v in ('poster','package','magnet') if v in b['deliverables']):
        spec = b['applications'][name]
        for key in ('width_mm', 'height_mm'):
            size = t.number(spec[key], name+key, True)
            if not 20 <= size <= 2000:
                raise ValueError('应用尺寸应在20至2000毫米之间')
            spec[key] = size
        if name != 'magnet':
            spec['repeat_width_mm'] = t.number(spec['repeat_width_mm'], '应用纹样周期宽', True)
    if 'magnet' in b['deliverables']:
        magnet=b['applications']['magnet']
        if magnet['mode'] not in ('motif_tiles','connected_quadrants'):
            raise ValueError('磁贴模式仅支持motif_tiles或connected_quadrants')
        if magnet['presentation'] not in ('flat','product'):
            raise ValueError('磁贴表现仅支持flat或product')
    if 'package' in b['deliverables'] and not 20 <= b['applications']['package']['depth_mm'] <= 2000:
        raise ValueError('包装深度应在20至2000毫米之间')
    if b.get('prompt_tasks') and '01-提取线稿' in b['prompt_tasks'] and not (source and extracted_path):
        raise ValueError('提取提示词需要实际原型对照和提取单元；不能以成纹去色替代提取')
    for spec in (b.get('colorways',[]) if 'fabric' in b['deliverables'] else []):
        if not spec.get('name'):
            raise ValueError('面料配色需要名称')
        for key in ('foreground', 'background'):
            if spec[key] not in b['palette']:
                raise ValueError('面料配色引用未知颜色角色')
        if b['palette'][spec['foreground']] == b['palette'][spec['background']]:
            raise ValueError('面料配色的主纹与背景不能同色')
    if 'fabric' in b['deliverables'] and not 1 <= len(b.get('colorways', [])) <= 4:
        raise ValueError('本平面面料展示支持一至四款配色')
    assets = {key: resolve(path, value) for key, value in b.get('brand_assets', {}).items() if value}
    for asset in assets.values():
        t.read_svg(asset)
    references = {key: resolve(path, value) for key, value in b.get('product_references', {}).items() if value}
    describe(b, layout)
    return {'brief_path': path, 'brief': b, 'unit': unit_path, 'extracted': extracted_path,
            'source': source, 'color_map': color_map, 'layout': layout, 'assets': assets, 'references': references}


def describe(b, layout):
    """文案参数从实际配置推导；不使用旧案例残留的sizes/repeat字段。"""
    b['sizes']={'海报':'本次未请求','包装':'本次未请求','磁贴':'本次未请求'}
    if 'magnet' in b['deliverables']:
        magnet=b['applications']['magnet'];magnet.setdefault('mode','motif_tiles');magnet.setdefault('presentation','product')
        b['magnet_mode']=magnet['mode']
        b['magnet_rule']=('将同一完整单元画面按中线拆成左上、右上、左下、右下四块；原位2×2拼回同一图案，块内不得各自重新居中、增删线条或换色。组合图无间隙，另展示相同四块的拆分图'
            if magnet['mode']=='connected_quadrants' else '四枚独立底板各保留完整单元；展示2×2摆放与拆分，仅表达自由摆放，不宣称拼回连续建筑或无缝连接')
        b['magnet_presentation']=(f"平面设计图，画板底色{b['palette']['纸面']}，主纹{b['palette']['轮廓带']}，图案负形与背景{b['palette']['负形与背景']}；无摄影、材质、投影或冰箱背景，标明组合与拆分，逐枚配色沿实际参照"
            if magnet['presentation']=='flat' else '哑光材质、浅灰冰箱门、柔和光线；照片级效果候选，另保留平面母版')
        b['sizes']['磁贴']=f"四枚独立方形/矩形底板，每枚{magnet['width_mm']:g}×{magnet['height_mm']:g}毫米；组合与拆分均展示"
    if 'package' in b['deliverables']:
        package=b['applications']['package'];package.setdefault('depth_assumed','depth_mm' not in package)
        if not isinstance(package['depth_assumed'],bool):raise ValueError('depth_assumed必须为布尔值')
        package['depth_mm']=t.number(package.get('depth_mm',min(package['width_mm'],package['height_mm'])/4),'包装深度',True)
        b['package_layout_size']=f"{2*package['width_mm']+2*package['depth_mm']:g}×{package['height_mm']+2*package['depth_mm']:g}毫米"
        b['package_depth_note']=f"深度{package['depth_mm']:g}毫米（"+('概念假设，未由用户或刀版确认' if package['depth_assumed'] else '本次需求给定，仍需核对刀版')+'）'
        b['sizes']['包装']=f"{package['width_mm']:g}×{package['height_mm']:g}毫米，正面概念"
    if 'poster' in b['deliverables']:
        spec=b['applications']['poster'];b['sizes']['海报']=f"{spec['width_mm']:g}×{spec['height_mm']:g}毫米"
    positions = '；'.join(f"位置{n+1}：x={t.number(p.get('x',0),'排列x'):g}、y={t.number(p.get('y',0),'排列y'):g}、旋转{t.number(p.get('rotate',0),'旋转'):g}度、等比缩放{t.number(p.get('scale',1),'缩放',True):g}、镜像{p.get('mirror','none')}" for n,p in enumerate(layout['placements']))
    b['repeat'] = f"完整重复块{layout['tile']['width']:g}×{layout['tile']['height']:g}个母版坐标单位；{positions}；以连续参照核对实际图地和连接关系"
