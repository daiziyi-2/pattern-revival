"""复核本地数字交付的实际文件与结构；不替代来源核查、审图或实物验收。"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import io
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import pattern_tools as t


def audit(case):
    case = Path(case).resolve()
    brief = json.loads((case/'设计需求.json').read_text(encoding='utf-8'))
    checks = []
    def record(name, status, evidence):
        checks.append({'name': name, 'status': status, 'evidence': evidence})
    scope=brief.get('deliverables',['poster','package','magnet','fabric'])
    required=['unit-master.svg','unit-color.svg','unit-lineart.svg','tile-color.svg',
              'repeat-3x3.svg','repeat-edges.svg','lineart-3x3.svg']
    if 'poster' in scope:required.append('poster-brand.svg')
    if 'package' in scope:required+=['package-front.svg','package-layout.svg']
    if 'fabric' in scope:required.append('fabric-colorways.svg')
    if 'magnet' in scope:required+=['magnet-modules.svg',*[f'magnet-module-{i}.svg' for i in range(1,5)]]
    connected='magnet' in scope and brief['applications']['magnet']['mode']=='connected_quadrants'
    if connected:
        required.append('magnet-assembly.svg')
    for name in required:
        path = case/name
        try:
            root = t.read_svg(path, strict=False)
            found = [s for s in t.issues(root) if any(token in s for token in
                     ('外部','位图','事件','重复 ID','未定义'))]
            if not any(t.tag(el) in t.SHAPES for el in root.iter()):
                found.append('无实际可编辑图形')
            if any(t.tag(el) in ('image','script','foreignObject') for el in root.iter()):
                found.append('含位图或非静态元素')
            record('文件：'+name, '需修正' if found else '通过', found or [name])
        except (OSError, ValueError, ET.ParseError) as exc:
            record('文件：'+name, '需修正', str(exc))
    for before,after,name in [('unit-master.svg','unit-color.svg','单元换色保持几何'),
                              ('unit-color.svg','unit-lineart.svg','单元去色保持几何'),
                              ('tile-color.svg','tile-lineart.svg','连续去色保持几何')]:
        try:
            same = t.geometry(t.read_svg(case/before)) == t.geometry(t.read_svg(case/after))
            record(name, '通过' if same else '需修正', [before,after])
        except (OSError, ValueError) as exc:
            record(name,'需修正',str(exc))
    for stem,key in [('poster-brand','poster'),('package-front','package'),('magnet-module-1','magnet')]:
        if key not in scope:continue
        try:
            root=t.read_svg(case/(stem+'.svg'),strict=False);spec=brief['applications'][key]
            correct=all(root.get(attr)==f'{spec[value]:g}mm' for attr,value in [('width','width_mm'),('height','height_mm')])
            record(stem+'实际尺寸','通过' if correct else '需修正',[stem+'.svg',spec])
        except (OSError, ValueError) as exc:
            record(stem+'实际尺寸','需修正',str(exc))
    try:
        if 'poster' in scope:
            root=t.read_svg(case/'poster-brand.svg',strict=False)
            titles=[el for el in root.iter() if t.tag(el)=='text' and el.get('data-role')=='main-title']
            count=len(titles)
            if titles and titles[0].text!=brief['poster_title']:count=0
            record('海报主标题仅一次','通过' if count==1 else '需修正',{'count':count})
    except (OSError, ValueError) as exc:
        record('海报主标题仅一次','需修正',str(exc))
    manifest=json.loads((case/'跨AI提示词/提示词清单.json').read_text(encoding='utf-8'))
    ref_checks=[]
    for job in manifest['jobs']:
        for ref in job['references']:
            path=(case/'跨AI提示词'/ref['file']).resolve()
            valid=(case/'跨AI提示词').resolve() in path.parents and path.is_file()
            valid=valid and hashlib.sha256(path.read_bytes()).hexdigest()==ref['sha256']
            ref_checks.append(valid)
    record('提示词引用真实且未被替换','通过' if ref_checks and all(ref_checks) else '需修正','跨AI提示词/提示词清单.json')
    seam_path=case/'seams.json'
    seam_valid=False
    if seam_path.is_file():
        seam=json.loads(seam_path.read_text(encoding='utf-8'))
        bindings={'input_sha256':'tile-color.svg','config_sha256':'layout-color.json','unit_sha256':'unit-color.svg'}
        seam_valid=seam.get('periodic_render_match') is True and all(
            (case/name).is_file() and seam.get(key)==hashlib.sha256((case/name).read_bytes()).hexdigest()
            for key,name in bindings.items())
    record('重复接缝像素检查','待检查' if not seam_path.is_file() else ('通过' if seam_valid else '需修正'),
           'seams.json与当前母版、重复块、配置指纹；构成质量另需审图')
    if connected:
        if all(importlib.util.find_spec(m) for m in ('resvg_py','PIL')):
            import resvg_py
            from PIL import Image, ImageChops, ImageStat
            try:
                images=[Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_path=str(case/file),width=600,dpi=96))).convert('RGBA')
                        for file in ('magnet-assembly.svg','magnet-assembly-reference.svg')]
                same_size=images[0].size==images[1].size
                difference=max(ImageStat.Stat(ImageChops.difference(*images)).mean) if same_size else 255
                record('四块拼回母版画面','通过' if difference<.5 else '需修正',
                       {'mean_difference':difference,'limit':.5,'files':['magnet-assembly.svg','magnet-assembly-reference.svg']})
            except (OSError, ValueError) as exc:
                record('四块拼回母版画面','需修正',str(exc))
        else:
            record('四块拼回母版画面','待检查','缺少渲染依赖；不以布局参数代替画面检查')
    source_files=[p.name for p in case.iterdir() if p.stem in ('source-reference','bag-reference','packaging-reference','magnet-reference')
                  and p.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.svg')]
    inventory={'references':[{'file':name,'is_deliverable':False,'role':'原型或载体参考，不计作生成成果'} for name in source_files],
               'generated':[{'file':name,'sha256':hashlib.sha256((case/name).read_bytes()).hexdigest(),
                             'identity':'可编辑数字稿/概念，非实物'} for name in required if (case/name).is_file()]}
    pending=[{'name':name,'status':'待人工核对'} for name in
             ('原型选区与提取准确性','连续构成与来源特征','海报字图关系及可读性','品牌风格与色值','目标软件打开','刀版与实物工艺','豆包实际复现')]
    return {'status':'需修正' if any(c['status']=='需修正' for c in checks) else '数字检查完成，人工项目待核对',
            'automatic_checks':checks,'manual_checks':pending,'inventory':inventory,
            'scope':'仅本次本地数字交付；参考图不计为输出，未验证项不写通过'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',required=True)
    args=parser.parse_args(argv)
    try:
        report=audit(args.case)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 2 if report['status']=='需修正' else 0
    except (OSError,ValueError,KeyError) as exc:
        print('错误：'+str(exc),file=sys.stderr);return 2


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
