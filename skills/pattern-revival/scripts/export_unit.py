#!/usr/bin/env python3
"""从 PDF 兼容 AI/PDF 的明确路径选取中导出 SVG；不做照片自动描摹。"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
import pattern_tools as tools


def rgb(value):
    if value is None:
        return 'none'
    if len(value) != 3:
        raise ValueError('选定路径需为可转换的 RGB 颜色')
    return '#' + ''.join(f'{max(0, min(255, round(c*255))):02x}' for c in value)


def path_data(drawing):
    parts, current, first = [], None, None
    def point(p):
        return f'{tools.fmt(p.x)} {tools.fmt(p.y)}'
    def begin(p):
        nonlocal current, first
        if current is None or abs(current.x-p.x)+abs(current.y-p.y) > .0001:
            parts.append('M'+point(p)); first = p
        current = p
    for item in drawing['items']:
        kind = item[0]
        if kind == 'c':
            begin(item[1]); parts.append('C'+' '.join(point(p) for p in item[2:5])); current = item[4]
        elif kind == 'l':
            begin(item[1]); parts.append('L'+point(item[2])); current = item[2]
        elif kind == 're':
            r = item[1]
            corners = [r.tl, r.tr, r.br, r.bl] if item[2] >= 0 else [r.tl, r.bl, r.br, r.tr]
            parts.append('M'+point(corners[0])+' '+' '.join('L'+point(p) for p in corners[1:])+' Z')
            current = first = None
        elif kind == 'qu':
            q = item[1]
            parts.append('M'+point(q.ul)+' L'+point(q.ur)+' L'+point(q.lr)+' L'+point(q.ll)+' Z')
            current = first = None
        else:
            raise ValueError(f'不支持路径操作 {kind}，请在矢量软件导出')
        if current is not None and first is not None and abs(current.x-first.x)+abs(current.y-first.y) <= .0001:
            parts.append('Z'); current = first = None
    if drawing.get('closePath') and current is not None:
        parts.append('Z')
    return ' '.join(parts)


def export(source, selection, output, overwrite=False):
    try:
        import pymupdf
    except ImportError:
        raise ValueError('路径导出需要可选 PyMuPDF；已打包单元的离线排列不需要此依赖')
    source, selection = Path(source).resolve(), Path(selection).resolve()
    if Path(output).resolve() in {source, selection}:
        raise ValueError('输出不能覆盖源文件或选择配置')
    spec = json.loads(selection.read_text(encoding='utf-8-sig'))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if spec.get('source_sha256') != digest:
        raise ValueError('源文件指纹与路径选择不一致，需重新核对页码和路径索引')
    page_index = spec['page_index']
    indices = spec['drawing_indices']
    if not isinstance(page_index, int) or isinstance(page_index, bool) or page_index < 0:
        raise ValueError('page_index 为从 0 开始的非负整数')
    if not isinstance(indices, list) or not indices or len(set(indices)) != len(indices):
        raise ValueError('drawing_indices 需为非空、不重复索引列表')
    with pymupdf.open(source) as doc:
        if page_index >= len(doc):
            raise ValueError('指定页不存在')
        page = doc[page_index]
        drawings = page.get_drawings()
        selected = []
        for i in indices:
            if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(drawings):
                raise ValueError('路径索引超出范围')
            selected.append(drawings[i])
        # 保留剪裁上下文；拒绝无法由简单 SVG 组表示的透明混合。
        selected_seq = {d['seqno'] for d in selected}
        levels, contexts = {}, {}
        for item in page.get_drawings(extended=True):
            level = item.get('level', 0)
            levels = {k: v for k, v in levels.items() if k < level}
            if item['type'] in {'clip', 'group'}:
                levels[level] = item
            elif item.get('seqno') in selected_seq:
                contexts[item['seqno']] = list(levels.values())
                for context in levels.values():
                    if context['type'] == 'group' and (context.get('opacity', 1) != 1 or
                            context.get('blendmode', 'Normal') != 'Normal' or context.get('knockout')):
                        raise ValueError('选定路径依赖透明混合组，请先在矢量软件整理')
        bounds = pymupdf.Rect(selected[0]['rect'])
        for d in selected[1:]:
            bounds |= d['rect']
        margin = max((d.get('width') or 0)/2 for d in selected)+2
        viewport = [bounds.x0-margin, bounds.y0-margin, bounds.width+2*margin, bounds.height+2*margin]
        root = tools.canvas(viewport[2], viewport[3])
        root.set('viewBox', ' '.join(tools.fmt(v) for v in viewport))
        title = tools.node('title'); title.text = spec['name']; root.append(title)
        defs = tools.node('defs'); root.append(defs)
        for index, d in zip(indices, selected):
            attrs = {'id': f'source-path-{index}', 'd': path_data(d), 'fill': rgb(d['fill']), 'stroke': rgb(d['color'])}
            if d['fill'] is not None:
                attrs.update({'fill-rule': 'evenodd' if d['even_odd'] else 'nonzero', 'fill-opacity': tools.fmt(d['fill_opacity'])})
            if d['color'] is not None:
                caps = d.get('lineCap') or (0, 0, 0)
                if len(set(caps)) != 1:
                    raise ValueError('路径含不同端点类型，请在矢量软件整理')
                attrs.update({'stroke-width': tools.fmt(d['width']),
                              'stroke-opacity': tools.fmt(d['stroke_opacity']),
                              'stroke-linecap': ['butt', 'round', 'square'][int(caps[0])],
                              'stroke-linejoin': ['miter', 'round', 'bevel'][int(d['lineJoin'])]})
                if d.get('dashes') and d['dashes'] != '[] 0':
                    raise ValueError('暂不支持虚线路径导出')
            parent = root
            for j, context in enumerate(contexts.get(d['seqno'], [])):
                if context['type'] == 'clip':
                    # 整页矩形若完全包住该路径含描边，移除这条冗余裁切；保留真正起作用的裁切。
                    items = context['items']
                    visual = pymupdf.Rect(d['rect'])
                    half = (d.get('width') or 0)/2
                    visual = visual + (-half, -half, half, half)
                    if len(items) == 1 and items[0][0] == 're' and items[0][1].contains(visual):
                        continue
                    clip_id = f'source-clip-{index}-{j}'
                    clip = tools.node('clipPath', {'id': clip_id, 'clipPathUnits': 'userSpaceOnUse'})
                    clip.append(tools.node('path', {'d': path_data(context),
                                'clip-rule': 'evenodd' if context['even_odd'] else 'nonzero'}))
                    defs.append(clip)
                    group = tools.node('g', {'clip-path': f'url(#{clip_id})'})
                    parent.append(group); parent = group
            parent.append(tools.node('path', attrs))
        if tools.issues(root):
            raise ValueError('导出路径不符合本地工具输入要求')
        tools.write_svg(root, output, overwrite, {'operation': 'export-unit', 'input': str(source),
                        'input_sha256': digest, 'selection': spec, 'source_bounds': list(bounds),
                        'output_viewBox': viewport, 'source_identity': '从团队可编辑文件的 PDF 兼容内容导出实际路径',
                        'limitations': '不保留 Illustrator 专有图层、CMYK 色空间或编辑历史；SVG 为 RGB 可编辑路径'})


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True); p.add_argument('--selection', required=True)
    p.add_argument('--output', required=True); p.add_argument('--overwrite', action='store_true')
    a = p.parse_args(argv)
    try:
        export(a.source, a.selection, a.output, a.overwrite); return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print('错误：'+str(exc), file=sys.stderr); return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
