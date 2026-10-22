"""按确定母版分割四块磁贴；拼回时保留同一整体画面，不猜测切割工艺。"""
from __future__ import annotations
import pattern_tools as t


def fit(root, source, x, y, width, height, prefix):
    vx, vy, sw, sh = t.viewbox(source)
    scale = min(width / sw, height / sh)
    dx, dy = x + (width - sw * scale) / 2, y + (height - sh * scale) / 2
    group = t.node('g', {'transform': f'translate({dx} {dy}) scale({scale}) translate({-vx} {-vy})'})
    group.append(t.group_from(source, prefix))
    root.append(group)


def split(unit, width, height, background):
    modules = []
    assembly = t.canvas(2 * width, 2 * height, background)
    reference = t.canvas(2 * width, 2 * height, background)
    fit(reference, unit, 0, 0, 2 * width, 2 * height, 'reference-')
    records = []
    for index in range(4):
        row, col = divmod(index, 2)
        module = t.canvas(width, height, background)
        clip_id = f'quadrant-{index}'
        defs = t.node('defs')
        clip = t.node('clipPath', {'id': clip_id, 'clipPathUnits': 'userSpaceOnUse'})
        clip.append(t.node('rect', {'x': 0, 'y': 0, 'width': width, 'height': height}))
        defs.append(clip); module.append(defs)
        group = t.node('g', {'clip-path': f'url(#{clip_id})'})
        fit(group, unit, -col * width, -row * height, 2 * width, 2 * height, f'unit-{index}-')
        module.append(group)
        placed = t.node('g', {'transform': f'translate({col * width} {row * height})'})
        placed.append(t.group_from(module, f'assembly-{index}-')); assembly.append(placed)
        modules.append(module)
        records.append({'file': f'magnet-module-{index+1}.svg', 'row': row, 'column': col,
                        'assembly_position_mm': [col * width, row * height],
                        'size_mm': [width, height]})
    return modules, assembly, reference, {'mode': 'connected_quadrants', 'master': 'unit-color.svg',
        'master_geometry': t.geometry(unit), 'assembly_size_mm': [2 * width, 2 * height],
        'modules': records, 'rule': '整体等比适配后四等分；组合无缝隙，不逐块重排图案',
        'physical_connection': '独立底板磁吸概念，未验证吸力、切割容差或实物工艺'}
