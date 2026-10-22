#!/usr/bin/env python3
"""静态 SVG 的排列、预览、属性编辑与几何检查；不处理照片提取。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
import io
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

SVG = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'
ET.register_namespace('', SVG)
ET.register_namespace('xlink', XLINK)
SHAPES = {'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon'}
ALLOWED = SHAPES | {'svg', 'g', 'defs', 'clipPath', 'pattern', 'use', 'title', 'desc', 'metadata'}
PAINT = {'fill', 'stroke', 'color', 'stroke-width', 'stroke-linecap', 'stroke-linejoin',
         'stroke-miterlimit', 'fill-opacity', 'stroke-opacity', 'opacity'}
STYLE_ALLOWED = PAINT | {'fill-rule', 'clip-rule', 'clip-path', 'stroke-dasharray',
                        'stroke-dashoffset', 'vector-effect', 'display', 'visibility'}


def tag(el):
    return el.tag.rsplit('}', 1)[-1]


def node(name, attrs=None):
    return ET.Element(f'{{{SVG}}}{name}', {k: str(v) for k, v in (attrs or {}).items()})


def number(value, name, positive=False):
    if isinstance(value, bool):
        raise ValueError(f'{name} 不能是布尔值')
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f'{name} 必须是有限' + ('正数' if positive else '数值'))
    return result


def fmt(value):
    return format(float(value), '.12g')


def style(el):
    result = {}
    for part in el.get('style', '').split(';'):
        if not part.strip():
            continue
        if ':' not in part:
            raise ValueError('无法解析内联 style，请先在矢量软件整理')
        key, value = part.split(':', 1)
        result[key.strip().lower()] = value.strip()
    return result


def put_style(el, values):
    if values:
        el.set('style', ';'.join(f'{k}:{v}' for k, v in values.items()))
    else:
        el.attrib.pop('style', None)


def color(value, allow_none=False):
    v = value.strip().lower()
    v = {'black': '#000000', 'white': '#ffffff'}.get(v, v)
    if allow_none and v == 'none':
        return v
    if re.fullmatch(r'#[0-9a-f]{3}', v):
        v = '#' + ''.join(x * 2 for x in v[1:])
    if not re.fullmatch(r'#[0-9a-f]{6}', v):
        raise ValueError('颜色使用 #RRGGBB 或 #RGB；背景可用 none')
    return v


def viewbox(root):
    if root.get('viewBox'):
        parts = re.split(r'[\s,]+', root.get('viewBox').strip())
        if len(parts) != 4:
            raise ValueError('viewBox 应为四个数')
        x, y, w, h = [number(v, 'viewBox') for v in parts]
    else:
        x = y = 0
        try:
            w, h = float(root.get('width', '')), float(root.get('height', ''))
        except ValueError:
            raise ValueError('需要 viewBox 或以数值像素表示的 width/height')
    number(w, '宽度', True)
    number(h, '高度', True)
    return x, y, w, h


def issues(root):
    found = []
    for el in root.iter():
        name = tag(el)
        if name not in ALLOWED:
            found.append(f'不支持元素 {name}')
        if el.get('class'):
            found.append('不支持 CSS class；请转为内联属性')
        for key, value in el.attrib.items():
            local = key.rsplit('}', 1)[-1]
            if local.lower().startswith('on'):
                found.append('包含事件属性')
            if local == 'href' and not value.startswith('#'):
                found.append('包含外部引用或位图数据')
            if re.search(r'url\((?!\s*[\"\']?#)', value, re.I):
                found.append('包含外部 URL')
            if '!important' in value:
                found.append('不支持 !important')
        try:
            for prop in style(el):
                if prop not in STYLE_ALLOWED:
                    found.append(f'不支持样式 {prop}')
        except ValueError as exc:
            found.append(str(exc))
        for attr in ('fill', 'stroke'):
            value = style(el).get(attr, el.get(attr, ''))
            if value and value not in ('none', 'inherit', 'currentColor'):
                try:
                    color(value)
                except ValueError:
                    found.append(f'不支持 {attr} 值 {value}；请改成 HEX')
    ids = [el.get('id') for el in root.iter() if el.get('id')]
    if len(ids) != len(set(ids)):
        found.append('存在重复 ID')
    defined = set(ids)
    for el in root.iter():
        for key, value in el.attrib.items():
            if key.rsplit('}', 1)[-1] == 'href' and value.startswith('#') and value[1:] not in defined:
                found.append('存在未定义的 use 引用 ' + value)
            for ref in re.findall(r'url\(\s*[\"\']?#([^\s)\"\']+)', value):
                if ref not in defined:
                    found.append('存在未定义的 URL 引用 #' + ref)
    return sorted(set(found))


def read_svg(path, strict=True):
    data = Path(path).read_bytes()
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('不支持 DTD/实体，请导出静态 SVG')
    root = ET.fromstring(data)
    if root.tag != f'{{{SVG}}}svg':
        raise ValueError('需要带 SVG 命名空间的根元素')
    viewbox(root)
    found = issues(root)
    if strict and found:
        raise ValueError('；'.join(found))
    return root


def geometry(root):
    def visit(el):
        if tag(el) in {'title', 'desc', 'metadata'} or el.get('data-role') == 'background':
            return None
        attrs = {k: v for k, v in el.attrib.items() if k not in PAINT and k != 'style'}
        retained = {k: v for k, v in style(el).items() if k not in PAINT}
        if retained:
            attrs['style'] = retained
        return [el.tag, attrs, [v for child in el if (v := visit(child)) is not None]]
    return hashlib.sha256(json.dumps(visit(root), sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def renamed(root, prefix):
    result = copy.deepcopy(root)
    names = {el.get('id'): prefix + el.get('id') for el in result.iter() if el.get('id')}
    for el in result.iter():
        if el.get('id'):
            el.set('id', names[el.get('id')])
        for key, value in list(el.attrib.items()):
            if key.rsplit('}', 1)[-1] == 'href' and value.startswith('#'):
                value = '#' + names.get(value[1:], value[1:])
            value = re.sub(r'url\(\s*[\"\']?#([^\s)\"\']+)[\"\']?\s*\)',
                           lambda m: 'url(#' + names.get(m[1], m[1]) + ')', value)
            el.set(key, value)
    return result


def group_from(root, prefix):
    source = renamed(root, prefix)
    attrs = {k: v for k, v in source.attrib.items()
             if k not in {'width', 'height', 'viewBox', 'preserveAspectRatio', 'version', 'id'}}
    group = node('g', attrs)
    for child in source:
        group.append(child)
    return group


def canvas(w, h, background='none'):
    root = node('svg', {'width': fmt(w), 'height': fmt(h), 'viewBox': f'0 0 {fmt(w)} {fmt(h)}'})
    if background != 'none':
        root.append(node('rect', {'x': 0, 'y': 0, 'width': fmt(w), 'height': fmt(h),
                                  'fill': color(background), 'stroke': 'none', 'data-role': 'background'}))
    return root


def background_color(root):
    for child in root:
        if child.get('data-role') == 'background':
            return style(child).get('fill', child.get('fill', 'none'))
    return 'none'


def without_background(root):
    result = copy.deepcopy(root)
    for child in list(result):
        if child.get('data-role') == 'background':
            result.remove(child)
    return result


def destination(path, overwrite):
    path = Path(path)
    if path.exists() and not overwrite:
        raise ValueError(f'文件已存在：{path}；需要覆盖时指定 --overwrite')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_svg(root, output, overwrite, record):
    path = Path(output)
    sidecar = path.with_suffix('.record.json')
    if (path.exists() or sidecar.exists()) and not overwrite:
        raise ValueError('输出或记录已存在，请换版本名或指定 --overwrite')
    destination(path, overwrite)
    payload = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    record.update({'output': str(path.resolve()), 'output_sha256': hashlib.sha256(payload).hexdigest(),
                   'geometry_sha256': geometry(root), 'time_utc': datetime.now(timezone.utc).isoformat(),
                   'manual_checks': {'source_relation': '未检查', 'seams': '未检查', 'application_size': '未检查'}})
    path.write_bytes(payload)
    sidecar.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(path), 'record': str(sidecar)}, ensure_ascii=False))


def composition(config_path):
    """配置到重复块；同一实现也用于接缝的独立大画布参照。"""
    config_path = Path(config_path).resolve()
    cfg = json.loads(config_path.read_text(encoding='utf-8-sig'))
    unit_path = (config_path.parent / cfg['unit']).resolve()
    unit = read_svg(unit_path)
    vx, vy, uw, uh = viewbox(unit)
    w = number(cfg['tile']['width'], '重复宽度', True)
    h = number(cfg['tile']['height'], '重复高度', True)
    placements = cfg['placements']
    if not isinstance(placements, list) or not placements:
        raise ValueError('placements 需要至少一个定位')
    root = canvas(w, h, color(cfg.get('background', 'none'), True))
    root.set('overflow', 'hidden')
    defs = node('defs')
    motif = group_from(unit, 'pr-source-')
    motif.set('id', 'pr-unit')
    defs.append(motif)
    root.append(defs)
    # 仅由SVG视口裁切一次；同时用clipPath与嵌套视口会在平铺边缘产生双重抗锯齿细线。
    stamps = node('g')
    count = 0
    for placement in placements:
        x = number(placement.get('x', 0), 'x') % w
        y = number(placement.get('y', 0), 'y') % h
        angle = number(placement.get('rotate', 0), 'rotate') % 360
        scale = number(placement.get('scale', 1), 'scale', True)
        mirror = placement.get('mirror', 'none')
        if mirror not in {'none', 'x', 'y', 'xy'}:
            raise ValueError('mirror 使用 none/x/y/xy')
        radius = math.hypot(uw, uh) * scale
        nx, ny = math.ceil(radius / w) + 1, math.ceil(radius / h) + 1
        count += (2 * nx + 1) * (2 * ny + 1)
        if count > 10000:
            raise ValueError('周期复制超过 10000 个；请减小单元或整理重复配置')
        mx = -1 if 'x' in mirror else 1
        my = -1 if 'y' in mirror else 1
        local = f'scale({mx} {my}) translate({fmt(-uw if mx < 0 else 0)} {fmt(-uh if my < 0 else 0)}) translate({fmt(-vx)} {fmt(-vy)})'
        for iy in range(-ny, ny + 1):
            for ix in range(-nx, nx + 1):
                transform = (f'translate({fmt(x + ix * w)} {fmt(y + iy * h)}) '
                             f'rotate({fmt(angle)} {fmt(uw * scale / 2)} {fmt(uh * scale / 2)}) '
                             f'scale({fmt(scale)}) {local}')
                stamps.append(node('use', {'href': '#pr-unit', 'transform': transform}))
    root.append(stamps)
    return root, {'operation': 'compose', 'config': cfg,
              'input': str(unit_path), 'input_geometry_sha256': geometry(unit),
              'periodic_wrap': '按横纵周期复制并裁切；连接设计和可见接缝仍需检查'}


def compose(args):
    root, record = composition(args.config)
    if Path(args.output).resolve() == Path(record['input']).resolve():
        raise ValueError('不能覆盖单元母版，请使用新的输出路径')
    write_svg(root, args.output, args.overwrite, record)


def preview(args):
    tile = read_svg(args.input)
    vx, vy, w, h = viewbox(tile)
    if not 1 <= args.cols <= 20 or not 1 <= args.rows <= 20:
        raise ValueError('行列数应在 1–20 之间')
    root = canvas(w * args.cols, h * args.rows, background_color(tile))
    defs = node('defs')
    motif = group_from(without_background(tile), 'pr-preview-')
    motif.set('id', 'pr-preview-tile')
    defs.append(motif)
    root.append(defs)
    for y in range(args.rows):
        for x in range(args.cols):
            nested = node('svg', {'x': fmt(x * w), 'y': fmt(y * h), 'width': fmt(w),
                                 'height': fmt(h), 'viewBox': f'{fmt(vx)} {fmt(vy)} {fmt(w)} {fmt(h)}',
                                 'overflow': 'hidden'})
            nested.append(node('use', {'href': '#pr-preview-tile'}))
            root.append(nested)
    if args.edges:
        overlay = node('g', {'fill': 'none', 'stroke': '#ff0088', 'stroke-width': '0.7', 'stroke-dasharray': '3 3'})
        for x in range(1, args.cols):
            overlay.append(node('line', {'x1': fmt(x * w), 'x2': fmt(x * w), 'y1': 0, 'y2': fmt(h * args.rows)}))
        for y in range(1, args.rows):
            overlay.append(node('line', {'y1': fmt(y * h), 'y2': fmt(y * h), 'x1': 0, 'x2': fmt(w * args.cols)}))
        root.append(overlay)
    write_svg(root, args.output, args.overwrite, {'operation': 'preview', 'input': str(Path(args.input).resolve()),
              'cols': args.cols, 'rows': args.rows, 'edges': args.edges})


def paint(args):
    root = read_svg(args.input)
    before = geometry(root)
    mapping = {}
    for entry in args.map:
        old, new = entry.split('=', 1)
        mapping[color(old)] = color(new)
    if not mapping:
        raise ValueError('至少提供一项 --map 旧色=新色')
    count = 0
    for el in root.iter():
        styles = style(el)
        for attr in ('fill', 'stroke', 'color'):
            for target in (el.attrib, styles):
                if attr in target:
                    try:
                        key = color(target[attr])
                    except ValueError:
                        continue
                    if key in mapping:
                        target[attr] = mapping[key]
                        count += 1
        put_style(el, styles)
    if 'fill' not in root.attrib and 'fill' not in style(root) and '#000000' in mapping:
        root.set('fill', mapping['#000000'])
        count += 1
    if not count:
        raise ValueError('未找到指定颜色，检查属性或颜色标值')
    if geometry(root) != before:
        raise ValueError('几何检查失败，未写输出')
    write_svg(root, args.output, args.overwrite, {'operation': 'paint', 'input': str(Path(args.input).resolve()),
              'mapping': mapping, 'changed_attributes': count, 'geometry_unchanged': True})


def lineart(args):
    root = read_svg(args.input)
    before = geometry(root)
    ink = color(args.ink)
    for el in root.iter():
        name = tag(el)
        if name in {'title', 'desc', 'metadata'}:
            continue
        styles = style(el)
        for prop in PAINT:
            if prop in {'opacity', 'fill-opacity', 'stroke-opacity'}:
                el.attrib.pop(prop, None)
                styles.pop(prop, None)
        if el.get('data-role') == 'background':
            for prop in ('fill', 'stroke'):
                styles.pop(prop, None)
            el.set('fill', '#ffffff')
            el.set('stroke', 'none')
        elif name in SHAPES:
            for prop in ('fill', 'stroke'):
                styles.pop(prop, None)
            el.set('fill', 'none')
            el.set('stroke', ink)
            if args.stroke_width is not None:
                styles.pop('stroke-width', None)
                el.set('stroke-width', fmt(number(args.stroke_width, '线宽', True)))
        put_style(el, styles)
    if args.background == 'none':
        for parent in root.iter():
            for child in list(parent):
                if child.get('data-role') == 'background':
                    parent.remove(child)
    else:
        vx, vy, w, h = viewbox(root)
        if not any(el.get('data-role') == 'background' for el in list(root)):
            root.insert(0, node('rect', {'x': fmt(vx), 'y': fmt(vy), 'width': fmt(w), 'height': fmt(h),
                                       'fill': '#ffffff', 'stroke': 'none', 'data-role': 'background'}))
    if geometry(root) != before:
        raise ValueError('几何检查失败，未写输出')
    write_svg(root, args.output, args.overwrite, {'operation': 'lineart', 'input': str(Path(args.input).resolve()),
              'ink': ink, 'background': args.background, 'stroke_width': args.stroke_width,
              'geometry_unchanged': True, 'scope': '几何签名不含颜色/线宽/指定背景；轮廓转单线骨架不支持'})


def inspect_svg(args):
    root = read_svg(args.input, strict=False)
    found = issues(root)
    counts = {}
    for el in root.iter():
        counts[tag(el)] = counts.get(tag(el), 0) + 1
    result = {'file': str(Path(args.input).resolve()), 'viewBox': viewbox(root), 'elements': counts,
              'editable_shape_definitions': sum(counts.get(t, 0) for t in SHAPES),
              'embedded_images': counts.get('image', 0), 'supported_by_tools': not found,
              'issues': found, 'geometry_sha256': geometry(root), 'seams': '未检查'}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not found else 2


def compare(args):
    left, right = read_svg(args.before), read_svg(args.after)
    same = geometry(left) == geometry(right)
    print(json.dumps({'geometry_unchanged': same, 'before_sha256': geometry(left), 'after_sha256': geometry(right),
                      'scope': '路径/坐标/变换/层级/裁切；不含颜色、描边属性和指定背景'}, ensure_ascii=False, indent=2))
    return 0 if same else 2


def render(args):
    read_svg(args.input)
    try:
        import resvg_py
    except ImportError:
        raise ValueError('PNG 渲染需要可选 resvg-py；可先交付 SVG 并用宿主设计/渲染工具导出')
    path = destination(args.output, args.overwrite)
    if args.width is not None and not 1 <= args.width <= 10000:
        raise ValueError('PNG 宽度应在 1–10000 之间')
    background = color(args.background, True)
    path.write_bytes(resvg_py.svg_to_bytes(svg_path=str(Path(args.input).resolve()), width=args.width,
                                         background=None if background == 'none' else background))
    print(json.dumps({'output': str(path)}, ensure_ascii=False))


def check_seams(args):
    """比较裁切后平铺与不在内部边界裁切的周期参照，不能替代构成判断。"""
    try:
        import resvg_py
        from PIL import Image, ImageChops
    except ImportError:
        raise ValueError('接缝像素检查需要 resvg-py 和 Pillow；依赖缺失时只交付边界 SVG，记录未检查')
    if not 64 <= args.tile_pixels <= 2048:
        raise ValueError('每块横向像素应在 64–2048 之间')
    path = destination(args.output, args.overwrite)
    tile = read_svg(args.input)
    cfg_path = Path(args.config).resolve()
    cfg = json.loads(cfg_path.read_text(encoding='utf-8-sig'))
    w, h = number(cfg['tile']['width'], '宽度', True), number(cfg['tile']['height'], '高度', True)
    if viewbox(tile) != (0, 0, w, h):
        raise ValueError('重复块 viewBox 与参照配置周期不一致')
    if h / w > 8:
        raise ValueError('像素检查限定周期高宽比不超过 8；请改用设计软件检查')
    # 参照在整个 3×3 画布上组合，只在最外缘裁切；内部连接不依赖输入块。
    larger = copy.deepcopy(cfg)
    larger['unit'] = str((cfg_path.parent / cfg['unit']).resolve())
    larger['tile'] = {'width': w * 3, 'height': h * 3}
    larger['placements'] = []
    for y in range(3):
        for x in range(3):
            for p in cfg['placements']:
                q = dict(p)
                q['x'] = number(p.get('x', 0), 'x') % w + x * w
                q['y'] = number(p.get('y', 0), 'y') % h + y * h
                larger['placements'].append(q)
    tiled = canvas(w * 3, h * 3, background_color(tile))
    for y in range(3):
        for x in range(3):
            part = renamed(without_background(tile), f'check-{x}-{y}-')
            part.set('x', fmt(x * w)); part.set('y', fmt(y * h))
            part.set('overflow', 'hidden')
            tiled.append(part)
    with tempfile.TemporaryDirectory() as folder:
        temp_cfg = Path(folder) / 'reference.json'
        temp_cfg.write_text(json.dumps(larger), encoding='utf-8')
        reference, _ = composition(temp_cfg)
        def raster(root):
            return Image.open(io.BytesIO(resvg_py.svg_to_bytes(
                svg_string=ET.tostring(root, encoding='unicode'), width=args.tile_pixels * 3))).convert('RGBA')
        actual, expected = raster(tiled), raster(reference)
    # 合成白底后比较颜色；透明黑的 RGB 不参与错误判断。
    def white(im):
        bg = Image.new('RGBA', im.size, 'white'); bg.alpha_composite(im)
        return bg.convert('RGB')
    diff = ImageChops.difference(white(actual), white(expected))
    if args.diagnostics:
        for label, im in [('tiled', actual), ('reference', expected), ('difference', diff)]:
            diagnostic = path.with_name(path.stem+'-'+label+'.png')
            destination(diagnostic, args.overwrite)
            im.save(diagnostic)
    px, py = actual.width / 3, actual.height / 3
    band = max(3, round(args.tile_pixels * .015))
    windows = {}
    def stats(box):
        crop = diff.crop(box)
        values = list(crop.get_flattened_data() if hasattr(crop, 'get_flattened_data') else crop.getdata())
        maximum = max((max(v) for v in values), default=0)
        bad = sum(max(v) > 32 for v in values)
        return {'max_channel_difference': maximum, 'pixels_over_32': bad,
                'pixel_count': len(values), 'passed': bad / max(1, len(values)) <= .005}
    for i in (1, 2):
        windows[f'vertical_{i}'] = stats((round(i * px)-band, band, round(i * px)+band, actual.height-band))
        windows[f'horizontal_{i}'] = stats((band, round(i * py)-band, actual.width-band, round(i * py)+band))
        for j in (1, 2):
            windows[f'junction_{i}_{j}'] = stats((round(i*px)-band, round(j*py)-band, round(i*px)+band, round(j*py)+band))
    passed = all(v['passed'] for v in windows.values())
    result = {'operation': 'check-seams', 'input': str(Path(args.input).resolve()),
              'config': str(cfg_path), 'input_sha256': hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
              'config_sha256': hashlib.sha256(cfg_path.read_bytes()).hexdigest(),
              'unit_sha256': hashlib.sha256(Path(larger['unit']).read_bytes()).hexdigest(),
              'tile_pixels': args.tile_pixels, 'band_pixels': band, 'windows': windows,
              'periodic_render_match': passed, 'tolerance': '每窗通道差>32的像素比例不超过0.5%；允许边缘栅格化差异，非零容差证明',
              'scope': '重复块平铺与同配置直接周期绘制在接缝及四块交点的一致性；不证明连接设计、来源、审美或印刷合格',
              'composition_review': '未检查', 'time_utc': datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'report': str(path), 'periodic_render_match': passed}, ensure_ascii=False))
    return 0 if passed else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for name, fn in [('compose', compose), ('preview', preview), ('paint', paint), ('lineart', lineart),
                     ('inspect', inspect_svg), ('compare', compare), ('render', render), ('check-seams', check_seams)]:
        p = subs.add_parser(name)
        p.set_defaults(run=fn)
        if name == 'compose':
            p.add_argument('--config', required=True)
        elif name == 'compare':
            p.add_argument('--before', required=True)
            p.add_argument('--after', required=True)
        else:
            p.add_argument('--input', required=True)
        if name not in {'inspect', 'compare'}:
            p.add_argument('--output', required=True)
            p.add_argument('--overwrite', action='store_true')
        if name == 'preview':
            p.add_argument('--cols', type=int, default=3)
            p.add_argument('--rows', type=int, default=3)
            p.add_argument('--edges', action='store_true')
        if name == 'paint':
            p.add_argument('--map', action='append', default=[])
        if name == 'lineart':
            p.add_argument('--ink', default='#000000')
            p.add_argument('--background', choices=['white', 'none'], default='white')
            p.add_argument('--stroke-width', type=float)
        if name == 'render':
            p.add_argument('--width', type=int)
            p.add_argument('--background', default='none')
        if name == 'check-seams':
            p.add_argument('--config', required=True)
            p.add_argument('--tile-pixels', type=int, default=512)
            p.add_argument('--diagnostics', action='store_true')
    args = parser.parse_args(argv)
    try:
        if hasattr(args, 'output'):
            for key in ('input', 'before', 'after', 'config'):
                if hasattr(args, key) and Path(getattr(args, key)).resolve() == Path(args.output).resolve():
                    raise ValueError('输入与输出不能是同一文件，请保留母版')
        return args.run(args) or 0
    except (ValueError, KeyError, TypeError, OSError, ET.ParseError) as exc:
        print('错误：' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
