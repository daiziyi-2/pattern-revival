"""从需求指定的真实SVG单元准备连续、去色、参考和追溯文件。"""
from __future__ import annotations
import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
from pathlib import Path
import pattern_tools as t
import run_case


def prepare(profile, output, vector_only=False, fonts=None):
    output = Path(output).resolve(); b = profile['brief']
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('输出目录需为空，请保留原稿并使用新版本目录')
    skill = Path(__file__).resolve().parents[1]
    if output == skill or skill in output.parents:
        raise ValueError('交付目录必须在技能包外')
    inputs = [profile['unit'], profile['brief_path'], *profile['assets'].values(), *profile['references'].values()]
    inputs += [p for p in (profile['extracted'], profile['source']) if p]
    if any(output == p or output in p.parents for p in inputs):
        raise ValueError('输出不能覆盖输入或包含源文件的目录')
    output.mkdir(parents=True, exist_ok=True)
    operations = []
    def command(*args):
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
            code = t.main(list(map(str, args)))
        operations.append({'command': list(map(str,args)), 'exit_code': code})
        if code:
            raise ValueError(capture.getvalue().strip())
    def copy_asset(source, stem):
        target = output/(stem+source.suffix.lower()); shutil.copyfile(source, target)
        record = source.with_suffix('.record.json')
        if record.is_file():
            shutil.copyfile(record, output/(stem+'.source-record.json'))
        return target
    copy_asset(profile['unit'], 'unit-master')
    if profile['color_map']:
        args = ['paint', '--input', output/'unit-master.svg', '--output', output/'unit-color.svg']
        for source,target in profile['color_map'].items():
            args += ['--map', source+'='+target]
        command(*args)
    else:
        root = t.read_svg(profile['unit'])
        with contextlib.redirect_stdout(io.StringIO()):
            t.write_svg(root, output/'unit-color.svg', False, {'operation':'reuse-unit','input_sha256':hashlib.sha256(profile['unit'].read_bytes()).hexdigest()})
    command('compare','--before',output/'unit-master.svg','--after',output/'unit-color.svg')
    command('lineart','--input',output/'unit-color.svg','--stroke-width',b.get('line_width',1.5),'--output',output/'unit-lineart.svg')
    if profile['extracted']:
        copy_asset(profile['extracted'], 'unit-extracted')
        extracted_status = '复用已提供的提取/整理单元，详见来源说明'
    else:
        shutil.copyfile(output/'unit-lineart.svg', output/'unit-extracted.svg')
        extracted_status = '成纹母版去色副本，未执行原型提取，不能作为新照片提取成果'
    if profile['source']:
        copy_asset(profile['source'], 'source-reference')
    for key,path in profile['assets'].items():
        if key in ('symbol','foliage'):
            copy_asset(path,'brand-'+key)
    for key,path in profile['references'].items():
        if key in ('bag','packaging'):
            copy_asset(path,key+'-reference')
    layout = profile['layout'].copy()
    layout['unit']='unit-color.svg'; layout['background']=b['palette']['负形与背景']
    run_case.dump(output/'layout-color.json',layout)
    command('compose','--config',output/'layout-color.json','--output',output/'tile-color.svg')
    command('preview','--input',output/'tile-color.svg','--output',output/'repeat-3x3.svg')
    command('preview','--input',output/'tile-color.svg','--edges','--output',output/'repeat-edges.svg')
    command('lineart','--input',output/'tile-color.svg','--stroke-width',b.get('line_width',1.5),'--output',output/'tile-lineart.svg')
    command('preview','--input',output/'tile-lineart.svg','--output',output/'lineart-3x3.svg')
    can_render = not vector_only and importlib.util.find_spec('resvg_py') is not None
    if can_render:
        import resvg_py
        for stem in ['unit-master','unit-color','unit-lineart','unit-extracted','tile-color','tile-lineart','repeat-3x3','repeat-edges','lineart-3x3','brand-symbol','brand-foliage']:
            path = output/(stem+'.svg')
            if path.exists():
                bg = b['palette']['负形与背景'] if stem in ('brand-symbol','unit-color') else '#FFFFFF'
                (output/(stem+'.png')).write_bytes(resvg_py.svg_to_bytes(svg_path=str(path),width=1200,dpi=96,background=bg,font_files=fonts or None))
    seams = '未检查（纯矢量模式或缺少依赖）'
    if can_render and importlib.util.find_spec('PIL') is not None:
        command('check-seams','--input',output/'tile-color.svg','--config',output/'layout-color.json','--output',output/'seams.json','--diagnostics')
        seams = '通过（限报告所记的像素容差；构成另需审图）'
    run_case.dump(output/'source-card.json', {'case_id':b.get('case_id'), 'name':b['unit_name'],
                  'unit_master':'unit-master.svg','unit_sha256':hashlib.sha256(profile['unit'].read_bytes()).hexdigest(),
                  'source_note':b.get('source_note','已有单元复用，来源待核查'),
                  'features':b['features'],'extracted_identity':extracted_status,
                  'photo_extraction':'未执行新的照片提取','culture':b.get('culture',{'status':'待核查'})})
    # 输出需求重新指向交付目录，整个目录搬移后仍能运行，避免原机器绝对路径。
    portable = json.loads(json.dumps(b))
    portable['inputs']={'unit':'unit-master.svg'}
    if profile['extracted']:
        portable['inputs']['extracted_unit']='unit-extracted.svg'
    if profile['source']:
        portable['inputs']['source_reference']='source-reference'+profile['source'].suffix.lower()
    portable['unit_color_roles']=b.get('unit_color_roles',{})
    portable['brand_assets']={k:'brand-'+k+v.suffix.lower() for k,v in profile['assets'].items() if k in ('symbol','foliage')}
    portable['product_references']={k:k+'-reference'+v.suffix.lower() for k,v in profile['references'].items() if k in ('bag','packaging')}
    run_case.dump(output/'设计需求.json',portable)
    return {'render':can_render,'checks':{'recolor_geometry':'通过','lineart_geometry':'通过','periodic_render':seams,
                         'photo_extraction':'未执行新的照片提取','visual_application':'待看图','production':'未验证'},
            'operations':operations, 'extracted_identity':extracted_status}
