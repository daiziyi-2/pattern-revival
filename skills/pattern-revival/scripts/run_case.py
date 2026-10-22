#!/usr/bin/env python3
"""离线复现团队四瓣案例：真实单元、排列、配色、线稿、海报与腰封概念。"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import pattern_tools as tools
import apply_pattern

SKILL = Path(__file__).resolve().parents[1]


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def run(output, vector_only=False, fonts=None):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('案例输出目录需为空，请使用新的版本目录；不覆盖已有成果')
    if output == SKILL or SKILL in output.parents:
        raise ValueError('案例成果请保存到技能包以外')
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    operations = []
    def command(*args):
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
            code = tools.main(list(map(str, args)))
        operations.append({'command': list(map(str, args)), 'exit_code': code, 'result': capture.getvalue().strip()})
        if code:
            raise ValueError(capture.getvalue().strip())
    for stem in ('quatrefoil-team-extracted', 'quatrefoil-team-arrangement'):
        for suffix in ('.svg', '.record.json'):
            shutil.copyfile(SKILL/'assets'/'units'/(stem+suffix), output/(stem+suffix))
    shutil.copyfile(SKILL/'assets'/'cases'/'quatrefoil-extraction.png', output/'source-reference.png')
    source = json.loads((SKILL/'assets'/'cases'/'quatrefoil-extraction-selection.json').read_text(encoding='utf-8'))
    arranged_source = json.loads((SKILL/'assets'/'cases'/'quatrefoil-arrangement-selection.json').read_text(encoding='utf-8'))
    dump(output/'source-card.json', {
        'case': '四瓣形窗格镂空', 'source': source, 'arrangement_source': arranged_source,
        'selection': '提取对象为四瓣形孔洞，不选相邻六角花卉；对照见source-reference.png',
        'source_features': ['四个圆弧瓣', '四瓣转折的窄连接处', '双轮廓线'],
        'manual_intervention': '团队已完成人工提取与成纹整理，本程序读取这些实际路径；未执行照片自动提取',
        'version_relation': '提取双轮廓→团队粗描边单元→本次均匀错位排列→应用。粗描边改变来自团队源文件，操作历史未知',
        'cultural_origin': '待核查', 'usage_conditions': '团队提供设计输入；照片使用条件待核查',
        'new_elements': '无新增母版图形；海报与腰封的信息排版为本次新增',
        'unit_export': '保留必要裁切；移除完全包住路径的整页冗余矩形裁切。RGB转换不等于CMYK印刷定稿'})
    cfg = json.loads((SKILL/'assets'/'layouts'/'quatrefoil-team-stagger.json').read_text(encoding='utf-8'))
    cfg['unit'] = 'quatrefoil-team-arrangement.svg'
    dump(output/'layout.json', cfg)
    command('compose', '--config', output/'layout.json', '--output', output/'tile-source-colors.svg')
    palette = json.loads((SKILL/'assets'/'palettes'/'zhu-garden.json').read_text(encoding='utf-8'))
    command('paint', '--input', output/'tile-source-colors.svg', '--map', '#e483cf='+palette['colors']['粉色'],
            '--map', cfg['background']+'='+palette['colors']['蓝紫色'], '--output', output/'tile-color.svg')
    colored_cfg = json.loads(json.dumps(cfg))
    command('paint', '--input', output/'quatrefoil-team-arrangement.svg', '--map', '#e483cf='+palette['colors']['粉色'],
            '--output', output/'unit-color.svg')
    colored_cfg['unit'] = 'unit-color.svg'; colored_cfg['background'] = palette['colors']['蓝紫色']
    dump(output/'layout-color.json', colored_cfg)
    command('preview', '--input', output/'tile-color.svg', '--output', output/'repeat-3x3.svg')
    command('preview', '--input', output/'tile-color.svg', '--edges', '--output', output/'repeat-edges.svg')
    command('lineart', '--input', output/'tile-color.svg', '--stroke-width', '1.5', '--output', output/'tile-lineart.svg')
    command('preview', '--input', output/'tile-lineart.svg', '--output', output/'lineart-3x3.svg')
    command('compare', '--before', output/'tile-source-colors.svg', '--after', output/'tile-color.svg')
    command('compare', '--before', output/'tile-color.svg', '--after', output/'tile-lineart.svg')
    has_render = not vector_only and importlib.util.find_spec('resvg_py') is not None
    has_pixels = has_render and importlib.util.find_spec('PIL') is not None
    for filename, template in [('poster.svg', 'poster-quatrefoil.json'), ('sleeve-concept.svg', 'sleeve-quatrefoil.json')]:
        root, record = apply_pattern.application(output/'tile-color.svg', SKILL/'assets'/'layouts'/template)
        with contextlib.redirect_stdout(io.StringIO()):
            tools.write_svg(root, output/filename, False, record)
        if has_render:
            import resvg_py
            (output/filename).with_suffix('.png').write_bytes(resvg_py.svg_to_bytes(
                svg_path=str(output/filename), dpi=96, width=1200, font_files=fonts or None))
    if has_render:
        for filename in ['quatrefoil-team-extracted.svg', 'quatrefoil-team-arrangement.svg',
                         'repeat-3x3.svg', 'repeat-edges.svg', 'lineart-3x3.svg']:
            command('render', '--input', output/filename, '--output', (output/filename).with_suffix('.png'),
                    '--width', 1200, '--background', '#ffffff')
    seam_status = '未检查（矢量模式或缺少渲染依赖）'
    if has_pixels:
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
            code = tools.main(['check-seams', '--input', str(output/'tile-color.svg'), '--config', str(output/'layout-color.json'),
                               '--output', str(output/'seams.json'), '--diagnostics'])
        if not (output/'seams.json').exists():
            raise ValueError(capture.getvalue().strip())
        seam_status = '通过（限记录的像素容差）' if code == 0 else '需修正'
        operations.append({'command': 'check-seams', 'exit_code': code, 'result': capture.getvalue().strip()})
    elapsed = time.perf_counter()-started
    report = {'case': '团队四瓣形离线案例v1', 'status': '开发案例；构成、目标软件与工艺仍需验收',
              'time_utc': datetime.now(timezone.utc).isoformat(), 'measured_seconds': round(elapsed, 3),
              'timing_scope': '本机脚本从已准备单元到数字稿导出；不含照片提取、人工审图、设备打开与实物制作',
              'tools': {'python': sys.version.split()[0], 'renderer': 'resvg-py' if has_render else '未调用',
                        'image_generation': '未调用；本流程使用本地可编辑单元'},
              'checks': {'editable_paths': '通过（实际path，非嵌入位图）', 'recolor_geometry': '通过',
                         'lineart_geometry': '通过', 'periodic_render': seam_status,
                         'source_photo_extraction': '未执行；复用团队人工提取', 'cultural_origin': '待核查',
                         'composition': '未检查', 'visual_application': '未检查',
                         'target_software_open': '未检查', 'print_production': '未检查'},
              'color_roles': {'轮廓带': palette['colors']['粉色'], '背景/负形': palette['colors']['蓝紫色'],
                              'palette_status': palette['status']},
              'operations': operations,
              'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()}}
    dump(output/'case-report.json', report)
    notes = f'''# 四瓣形离线案例交付

本案例复用团队实际提取和成纹路径，完整呈现同案例的原型参照、提取单元、整理单元、重新排列、配色、线稿与应用。照片自动提取未执行；粗描边单元与提取双轮廓是两个版本，不能声称几何相同。来源地点及照片使用条件待核查。

## 文件入口

- [原型与提取参照](source-reference.png)、[来源与结构卡](source-card.json)
- [实际提取单元](quatrefoil-team-extracted.svg)、[实际成纹单元](quatrefoil-team-arrangement.svg)
- [排列参数](layout-color.json)、[独立重复块](tile-color.svg)、[3×3平铺](repeat-3x3.svg)、[边界标注](repeat-edges.svg)
- [白底黑线](tile-lineart.svg)、[线稿平铺](lineart-3x3.svg)
- [A3海报](poster.svg)、[240×80mm腰封概念展开](sleeve-concept.svg)
- [过程与文件指纹](case-report.json)

SVG 是可编辑路径；应用 SVG 另含可编辑文字，需在目标设备核对字体。PNG 若生成只作为预览。

## 检查状态

换色与线稿的几何比较通过。接缝像素检查：{seam_status}。构成、实际软件打开、应用版面及制作工艺未自动验收，见 case-report.json。包装尺寸是概念假设，非生产刀版。

本次本机数字导出用时 {elapsed:.2f} 秒，范围仅为准备好的本地单元到数字稿；不能据此承诺任意照片五分钟完成。
'''
    (output/'交付说明.md').write_text(notes, encoding='utf-8')
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True); p.add_argument('--vector-only', action='store_true')
    p.add_argument('--font', action='append', default=[])
    a = p.parse_args(argv)
    try:
        report = run(a.output, a.vector_only, a.font)
        print(json.dumps({'output': str(Path(a.output).resolve()), 'checks': report['checks']}, ensure_ascii=False))
        return 2 if report['checks']['periodic_render'] == '需修正' else 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print('错误：'+str(exc), file=sys.stderr); return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
