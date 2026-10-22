#!/usr/bin/env python3
"""导出实填、工具无关的中文提示词与可携带参考文件。"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
import delivery_profile

SKILL = Path(__file__).resolve().parents[1]


def export(case, output, brief=None, only=None):
    case, output = Path(case).resolve(), Path(output).resolve()
    if not case.is_dir():
        raise ValueError('成果目录不存在')
    if output == case or output == SKILL or SKILL in output.parents or output in case.parents:
        raise ValueError('提示词包不能写入母版目录、技能包或成果目录的上级')
    if output.exists() and any(output.iterdir()):
        raise ValueError('提示词输出目录需为空；请保存新版本')
    embedded = case/'设计需求.json'
    if not brief and not embedded.is_file():
        raise ValueError('缺少本次设计需求，请提供--brief；禁止默认套用四瓣或其他案例')
    brief_path, b = delivery_profile.read(brief or embedded)
    if embedded.is_file():
        _, actual = delivery_profile.read(embedded)
        if any(b.get(k) != actual.get(k) for k in ('case_id','unit_name','features','palette','repeat','sizes',
              'brand','poster_title','poster_subtitle','package_title','package_subtitle','copy','prompt_rules',
              'magnet_mode','magnet_rule','magnet_presentation','package_layout_size','package_depth_note','layout','applications','deliverables')):
            raise ValueError('需求与成果案例不一致，禁止混用其他纹样的提示词或参考')
    p = b['palette']; sizes = b['sizes']
    rules = b.get('prompt_rules', {})
    colorways = b.get('colorways') or [{'name': b['unit_name'], 'foreground': '轮廓带', 'background': '负形与背景'}]
    values = {**b, 'features': '、'.join(b['features']), 'band': p['轮廓带'], 'ground': p['负形与背景'],
              'red': p['朱红'], 'teal': p['园林青'], 'palette': '；'.join(f'{k}{v}' for k, v in p.items()),
              'poster_size': sizes['海报'], 'package_size': sizes['包装'], 'magnet_size': sizes['磁贴'],
              'extraction_target': rules.get('extraction_target', '只提取用户明确选定的结构，保留可见轮廓，不新增无依据细节'),
              'unit_rule': rules.get('unit', '以本次实际母版路径和图地关系为准'),
              'lineart_rule': rules.get('lineart', '保留现有轮廓、节点与填充区域的外边界，不改为另一种骨架'),
              'source_note': b.get('source_note', '已有单元直接应用；未执行照片提取，文化来源待核查'),
              'colorway_count': len(colorways),
              'colorway_description': '；'.join(c['name']+'（主纹'+p[c['foreground']]+'、背景'+p[c['background']]+'）' for c in colorways),
              'recolor_band': b.get('recolor', {}).get('foreground', p['园林青']),
              'recolor_ground': b.get('recolor', {}).get('background', p['朱红'])}
    values.update({'magnet_rule': b.get('magnet_rule', '四枚各自保留完整单元，仅自由摆放，不宣称连缀'),
                   'magnet_presentation': b.get('magnet_presentation', '照片级效果候选，需另保留平面母版'),
                   'package_layout_size': b.get('package_layout_size', '尺寸待核对'),
                   'package_depth_note': b.get('package_depth_note', '深度未指定，概念稿需注明假设')})
    templates = json.loads((SKILL/'assets/prompts/deliverables.json').read_text(encoding='utf-8'))
    if only:
        wanted = set(only)
        available = {j['id'] for j in templates}
        if wanted-available:
            raise ValueError('未知提示词项：'+', '.join(sorted(wanted-available)))
        templates = [j for j in templates if j['id'] in wanted]
    prepared = []
    for job in templates:
        body = job['body'].format_map(values)
        task_title = ('模块化磁贴平面复现' if job['id']=='07-模块磁贴' and
                      b.get('applications',{}).get('magnet',{}).get('presentation')=='flat' else job['title'])
        title = task_title+' · '+b['unit_name']
        refs = []; missing = []
        references = [(stem, role, True) for stem, role in job['references']]
        references += [(stem, role, False) for stem, role in job.get('optional_references', [])]
        for stem, role, required in references:
            # PNG优先，未渲染时带上SVG，并明确让用户先转成PNG。
            choices = [case/(stem+suffix) for suffix in ('.png', '.jpg', '.jpeg', '.webp', '.svg')]
            # 只读取本次成果或显式映射，不从技能包偷偷补入另一个案例。
            aliases = b.get('reference_files', {})
            if stem in aliases:
                explicit = (case/aliases[stem]).resolve()
                if case not in explicit.parents:
                    raise ValueError('参考映射必须在本次成果目录内')
                choices.insert(0, explicit)
            path = next((x for x in choices if x.is_file()), None)
            if path:
                kind = ('source' if stem == 'source-reference' else
                        'carrier' if stem in ('bag-reference', 'packaging-reference', 'magnet-reference') else
                        'brand' if stem.startswith('brand-') else
                        'unit' if stem.startswith('unit-') else
                        'pattern' if stem in ('repeat-3x3','repeat-edges','tile-color','lineart-3x3','fabric-colorways') else 'layout')
                refs.append((path, role, kind))
            elif required:
                missing.append({'name': stem, 'role': role})
        if not refs:
            raise ValueError(job['id']+'没有任何真实参考文件；请先生成对应成果')
        prepared.append(({**job, 'title': title}, body, refs, missing))
    output.mkdir(parents=True, exist_ok=True)
    refdir = output/'参考图'; refdir.mkdir(exist_ok=True)
    manifest = {'name': b['name'], 'status': '参考约束下复现设计方向；不承诺不同模型相同像素或路径',
                'brief': '设计需求.json', 'jobs': []}
    guide = ['# 跨 AI 提示词与参考包', '', '先选择下面的一项，复制完整TXT正文，再按该项的编号顺序上传参考图。',
             '有参考编辑模式时优先使用。只支持文字的工具可以探索相似方向，不能保证同一母版。',
             '带SVG的参考请先在浏览器/设计工具导出PNG；准确母版仍保留SVG。',
             '生成后核对本次单元的结构、排列、配色和中文；中文和精确路径以可编辑稿为准。', '']
    for job, body, refs, missing in prepared:
        lines = [f'任务：{job["title"]}', '', '参考图按以下顺序上传：']
        records = []
        for index, (path, role, kind) in enumerate(refs, 1):
            # 同名但内容不同不能误复用；内容指纹组成稳定文件名。
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            target = refdir/(path.stem+'-'+digest[:10]+path.suffix.lower())
            if not target.exists():
                shutil.copyfile(path, target)
            relative = target.relative_to(output).as_posix()
            note = '（先导出PNG再上传）' if path.suffix.lower() == '.svg' else ''
            lines.append(f'图{index}：{relative} — {role}{note}')
            if kind == 'carrier':
                lines.append('用途限制：此图只指导载体外形、材质与摄影，不提供纹样结构，也不计作本次生成成果。')
            records.append({'order': index, 'file': relative, 'role': role, 'sha256': digest,
                            'kind': kind, 'is_deliverable': False,
                            'upload_ready': path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')})
            # 同时提供准确源稿，支持后续矢量编辑；不要求图像平台能打开。
            svg = path.with_suffix('.svg')
            if path.suffix.lower() != '.svg' and svg.is_file():
                svg_digest = hashlib.sha256(svg.read_bytes()).hexdigest()
                svg_target = refdir/(svg.stem+'-'+svg_digest[:10]+'.svg')
                if not svg_target.exists():
                    shutil.copyfile(svg, svg_target)
        if missing:
            lines.extend(['', '未附参考：'+'；'.join(x['name']+'（'+x['role']+'）' for x in missing),
                          '本次未附成稿/载体的位置仅按正文探索；需要复现该成稿或载体时先补图。'])
        lines.extend(['', '完整提示词：', body, '', '执行：只完成这一项；要求多个独立文件时逐张生成并命名，不将流程、重复块和产品效果拼成一张成果图。',
                      '复核：保留'+values['features']+'与实际排列关系；核对准确文案。生成图为候选。',
                      '工具参数：在目标AI界面设置正文要求的画面比例；本包没有绑定模型、种子或专用参数。', ''])
        prompt = output/(job['id']+'.txt')
        prompt.write_text('\n'.join(lines), encoding='utf-8')
        manifest['jobs'].append({'id': job['id'], 'title': job['title'], 'prompt': prompt.name,
                                 'references': records, 'missing_references': missing,
                                 'ready': not missing and all(r['upload_ready'] for r in records)})
        status = '参考齐全，可直接上传' if manifest['jobs'][-1]['ready'] else '含待补图或待转PNG，详见正文'
        guide.append(f'- [{job["title"]}]({prompt.name})：{status}')
    prompt_brief = {k:v for k,v in b.items() if k not in ('inputs','brand_assets','product_references','unit_color_roles','layout','reference_files')}
    prompt_brief['purpose'] = '生图交接需求，参考文件见提示词清单；可重跑脚本需求在完整交付根目录'
    (output/'设计需求.json').write_text(json.dumps(prompt_brief, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (output/'提示词清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    guide += ['', '所有参考副本都在本目录的“参考图”中，整个目录可复制到另一台电脑。',
              '平面SVG与照片级产品效果分开：提示词不会自动生成图片，精确颜色、接缝、刀版和材质仍需检查。', '']
    (output/'使用说明.md').write_text('\n'.join(guide), encoding='utf-8')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True); parser.add_argument('--output', required=True)
    parser.add_argument('--brief'); parser.add_argument('--only', nargs='+')
    args = parser.parse_args(argv)
    try:
        manifest = export(args.case, args.output, args.brief, args.only)
        print(json.dumps({'output': str(Path(args.output).resolve()), 'items': len(manifest['jobs']),
                          'ready': sum(j['ready'] for j in manifest['jobs'])}, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print('错误：'+str(exc), file=sys.stderr); return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
