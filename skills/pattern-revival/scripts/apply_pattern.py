#!/usr/bin/env python3
"""将确定的连续母版用于有实际尺寸的平面 SVG 模板，文字保持可编辑。"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
import xml.etree.ElementTree as ET
import pattern_tools as tools


def application(tile_path, template_path):
    tile_path, template_path = Path(tile_path).resolve(), Path(template_path).resolve()
    tile = tools.read_svg(tile_path)
    template = json.loads(template_path.read_text(encoding='utf-8-sig'))
    width = tools.number(template['width_mm'], '应用宽度', True)
    height = tools.number(template['height_mm'], '应用高度', True)
    vx, vy, tw, th = tools.viewbox(tile)
    repeat = tools.number(template['repeat_width_mm'], '重复块印刷宽度', True)
    root = tools.canvas(width, height, tools.color(template['paper']))
    root.set('width', tools.fmt(width)+'mm'); root.set('height', tools.fmt(height)+'mm')
    title = tools.node('title'); title.text = template['name']; root.append(title)
    defs = tools.node('defs')
    pattern = tools.node('pattern', {'id': 'application-pattern', 'patternUnits': 'userSpaceOnUse',
                         'width': tools.fmt(repeat), 'height': tools.fmt(repeat*th/tw),
                         'viewBox': f'{tools.fmt(vx)} {tools.fmt(vy)} {tools.fmt(tw)} {tools.fmt(th)}'})
    pattern.append(tools.group_from(tools.without_background(tile), 'app-master-'))
    defs.append(pattern); root.append(defs)
    graphics = tools.node('g', {'id': 'pattern-layer'}); root.append(graphics)
    for area in template['pattern_areas']:
        x, y = tools.number(area['x'], '区域x'), tools.number(area['y'], '区域y')
        w, h = tools.number(area['width'], '区域宽', True), tools.number(area['height'], '区域高', True)
        if x < 0 or y < 0 or x+w > width+.0001 or y+h > height+.0001:
            raise ValueError('纹样区域超出页面')
        if tools.background_color(tile) != 'none':
            graphics.append(tools.node('rect', {'x': tools.fmt(x), 'y': tools.fmt(y),
                            'width': tools.fmt(w), 'height': tools.fmt(h), 'fill': tools.background_color(tile)}))
        graphics.append(tools.node('rect', {'x': tools.fmt(x), 'y': tools.fmt(y),
                        'width': tools.fmt(w), 'height': tools.fmt(h), 'fill': 'url(#application-pattern)'}))
    text_layer = tools.node('g', {'id': 'information-layer', 'fill': tools.color(template['ink']),
                           'font-family': template.get('font_family', 'Microsoft YaHei, Noto Sans CJK SC, sans-serif')})
    root.append(text_layer)
    for item in template['texts']:
        x, y = tools.number(item['x'], '文字x'), tools.number(item['y'], '文字y')
        size = tools.number(item['size'], '字号', True)
        if not 0 <= x <= width or not 0 <= y <= height:
            raise ValueError('文字位置超出页面')
        el = tools.node('text', {'x': tools.fmt(x), 'y': tools.fmt(y), 'font-size': tools.fmt(size),
                         'font-weight': item.get('weight', '400'), 'letter-spacing': item.get('tracking', '0')})
        el.text = str(item['text']); text_layer.append(el)
    return root, {'operation': 'apply-pattern', 'input': str(tile_path),
                  'input_sha256': hashlib.sha256(tile_path.read_bytes()).hexdigest(),
                  'input_geometry_sha256': tools.geometry(tile), 'template': template,
                  'template_sha256': hashlib.sha256(template_path.read_bytes()).hexdigest(),
                  'physical_size_mm': [width, height], 'repeat_size_mm': [repeat, repeat*th/tw],
                  'scale_mm_per_source_unit': repeat/tw,
                  'output_identity': template['status'], 'source_structure': '直接引用母版，仅缩放和区域裁切',
                  'limitations': 'SVG文字依赖目标设备字体；未作CMYK/出血/供应商工艺验证'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True); p.add_argument('--template', required=True)
    p.add_argument('--output', required=True); p.add_argument('--overwrite', action='store_true')
    p.add_argument('--render', action='store_true'); p.add_argument('--width', type=int, default=1200)
    p.add_argument('--font', action='append', default=[])
    a = p.parse_args(argv)
    try:
        output = Path(a.output).resolve()
        if output in {Path(a.input).resolve(), Path(a.template).resolve()}:
            raise ValueError('应用输出不能覆盖输入')
        if a.render:
            if not 64 <= a.width <= 5000:
                raise ValueError('预览宽度应在64–5000之间')
            import resvg_py
            tools.destination(output.with_suffix('.png'), a.overwrite)
        root, record = application(a.input, a.template)
        tools.write_svg(root, output, a.overwrite, record)
        if a.render:
            output.with_suffix('.png').write_bytes(resvg_py.svg_to_bytes(svg_path=str(output),
                        width=a.width, dpi=96, font_files=a.font or None))
        return 0
    except ImportError:
        print('错误：预览需要可选 resvg-py；不加 --render 可交付可编辑SVG', file=sys.stderr); return 2
    except (ValueError, KeyError, TypeError, OSError, ET.ParseError) as exc:
        print('错误：'+str(exc), file=sys.stderr); return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
