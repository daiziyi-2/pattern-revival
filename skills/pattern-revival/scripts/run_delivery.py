#!/usr/bin/env python3
"""从指定SVG与需求生成可编辑应用、连续纹样及跨AI交接包。"""
from __future__ import annotations
import argparse
import contextlib
import copy
import hashlib
import io
import json
import shutil
import sys
import time
import unicodedata
from pathlib import Path
import pattern_tools as t
import delivery_profile
import prepare_delivery
import export_prompts
import run_case
import magnet_modules
import delivery_audit

SKILL = Path(__file__).resolve().parents[1]


def rect(root,x,y,w,h,fill,**attrs):
    root.append(t.node('rect',{'x':x,'y':y,'width':w,'height':h,'fill':fill,**attrs}))


def text(root,x,y,content,size,fill='#222222',weight='400',max_width=None,role=None):
    units=sum(1 if unicodedata.east_asian_width(c) in ('W','F') else .62 for c in content)
    if max_width and units:
        size=min(size,max_width/units)
    el=t.node('text',{'x':x,'y':y,'font-size':size,'fill':fill,'font-weight':weight,
                     'font-family':'Microsoft YaHei, Noto Sans CJK SC, sans-serif'})
    el.text=content;root.append(el)
    if role: el.set('data-role',role)


def place(root,source,x,y,w,h,prefix,ink=None):
    source=copy.deepcopy(source)
    if ink:
        for el in source.iter():
            values=t.style(el)
            for key in ('fill','stroke'):
                value=values.get(key,el.get(key))
                if value not in (None,'none'):
                    if key in values:values[key]=ink
                    else:el.set(key,ink)
            t.put_style(el,values)
    vx,vy,sw,sh=t.viewbox(source);scale=min(w/sw,h/sh)
    dx,dy=x+(w-sw*scale)/2,y+(h-sh*scale)/2
    group=t.node('g',{'transform':f'translate({dx} {dy}) scale({scale}) translate({-vx} {-vy})'})
    group.append(t.group_from(source,prefix));root.append(group)


def area(root,tile,x,y,w,h,repeat,prefix):
    vx,vy,tw,th=t.viewbox(tile)
    defs=t.node('defs');pat=t.node('pattern',{'id':prefix,'patternUnits':'userSpaceOnUse',
        'x':x,'y':y,'width':repeat,'height':repeat*th/tw,'viewBox':f'{vx} {vy} {tw} {th}'})
    pat.append(t.group_from(t.without_background(tile),prefix+'-'));defs.append(pat);root.append(defs)
    rect(root,x,y,w,h,t.background_color(tile));rect(root,x,y,w,h,f'url(#{prefix})')


def recolor(root,mapping):
    result=copy.deepcopy(root)
    for el in result.iter():
        values=t.style(el)
        for key in ('fill','stroke','color'):
            value=values.get(key,el.get(key,''))
            if value.startswith('#'):
                value=t.color(value)
            if value in mapping:
                if key in values:values[key]=mapping[value]
                else:el.set(key,mapping[value])
        t.put_style(el,values)
    if t.geometry(result)!=t.geometry(root):
        raise ValueError('改色影响母版几何')
    return result


def readable_ink(background, preferred, paper):
    def luminance(color):
        values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
        linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
        return sum(v*k for v,k in zip(linear,(.2126,.7152,.0722)))
    bg=luminance(background)
    def contrast(ink):
        value=luminance(ink)
        return (max(bg,value)+.05)/(min(bg,value)+.05)
    return preferred if contrast(preferred)>=4.5 else (paper if contrast(paper)>=4.5 else max(('#FFFFFF','#000000'),key=contrast))


def run(output,vector_only=False,fonts=None,brief=None):
    started=time.perf_counter();profile=delivery_profile.validate(brief)
    b=profile['brief'];p=b['palette'];output=Path(output).resolve()
    report=prepare_delivery.prepare(profile,output,vector_only,fonts)
    tile=t.read_svg(output/'tile-color.svg');unit=t.read_svg(output/'unit-color.svg')
    symbol=t.read_svg(output/'brand-symbol.svg') if (output/'brand-symbol.svg').is_file() else None
    foliage=t.read_svg(output/'brand-foliage.svg') if (output/'brand-foliage.svg').is_file() else None
    specs=[]
    def save(root,stem,w=None,h=None,status='可编辑平面概念；非生产稿',details=None):
        if w and h:root.set('width',f'{w:g}mm');root.set('height',f'{h:g}mm')
        record={'operation':'delivery-application','identity':status,'master':'unit-color.svg',
                'master_geometry':t.geometry(unit),'repeat_master':'tile-color.svg',
                'physical_size_mm':[w,h] if w and h else None,
                'limitations':'文字需目标设备字体；未验证刀版、CMYK或实物工艺'}
        if details: record.update(details)
        with contextlib.redirect_stdout(io.StringIO()):t.write_svg(root,output/(stem+'.svg'),False,record)
        if report['render']:
            import resvg_py
            (output/(stem+'.png')).write_bytes(resvg_py.svg_to_bytes(svg_path=str(output/(stem+'.svg')),
                width=1400,dpi=96,font_files=fonts or None))
        specs.append({'file':stem+'.svg','status':status,'size_mm':record['physical_size_mm']})
    copy_text=b.get('copy',{})
    def build_poster():
        # 同一焦点：放大的单元构成窗框，品牌主题图形位于内部；连续纹样作底部边带。
        ps=b['applications']['poster'];w,h=ps['width_mm'],ps['height_mm'];sx,sy=w/297,h/420;fs=min(sx,sy)
        poster=t.canvas(w,h,p['纸面'])
        text(poster,22*sx,23*sy,b['brand'],6*fs,p['文字'],'700',w-44*sx)
        rect(poster,22*sx,35*sy,13*sx,2*sy,p['朱红'])
        text(poster,19*sx,107*sy,b['poster_title'],62*fs,p['文字'],'700',w-42*sx,role='main-title')
        text(poster,24*sx,132*sy,b['poster_subtitle'],8*fs,p['文字'],'400',w-48*sx)
        place(poster,unit,28*sx,148*sy,241*sx,172*sy,'poster-unit-')
        if symbol is not None and b.get('poster_use_symbol',True):
            place(poster,symbol,105*sx,196*sy,86*sx,70*sy,'poster-symbol-',p['负形与背景'])
        if foliage is not None:place(poster,foliage,16*sx,164*sy,36*sx,77*sy,'poster-foliage-',p['文字'])
        area(poster,tile,0,333*sy,w,34*sy,ps['repeat_width_mm'],'poster-border')
        copy_text=b.get('copy',{})
        text(poster,22*sx,393*sy,copy_text.get('series',b['unit_name']),5.5*fs,p['文字'],'700',w-44*sx)
        text(poster,22*sx,408*sy,copy_text.get('poster_footer',b['poster_subtitle']),4*fs,p['文字'],'400',w-44*sx)
        save(poster,'poster-brand',w,h)

    def build_package():
        # 包装保持明确品名层级，依实际母版与配色变化；不把正面概念伪装成展开刀版。
        pk=b['applications']['package'];w,h=pk['width_mm'],pk['height_mm'];sx,sy=w/240,h/164;fs=min(sx,sy)
        package=t.canvas(w,h,p['朱红'])
        variant=recolor(tile,{p['轮廓带']:p['园林青'],p['负形与背景']:p['朱红']})
        area(package,variant,0,0,153*sx,89*sy,pk['repeat_width_mm'],'package-top')
        area(package,variant,0,144*sy,w,20*sy,pk['repeat_width_mm'],'package-bottom')
        if foliage is not None:place(package,foliage,0,-8*sy,104*sx,108*sy,'package-foliage-',p['文字'])
        rect(package,170*sx,9*sy,56*sx,70*sy,p['负形与背景'])
        if symbol is not None:place(package,symbol,166*sx,12*sy,64*sx,63*sy,'package-symbol-','#FFFFFF')
        else:place(package,unit,172*sx,14*sy,52*sx,60*sy,'package-unit-')
        rect(package,0,89*sy,w,55*sy,p['园林青'])
        package_ink=readable_ink(p['园林青'],p['文字'],p['纸面'])
        text(package,9*sx,128*sy,b['package_title'],28*fs,package_ink,'700',119*sx)
        text(package,137*sx,111*sy,b['brand'],4.5*fs,package_ink,'700',93*sx)
        text(package,137*sx,121*sy,b['package_subtitle'],4.2*fs,package_ink,'400',93*sx)
        text(package,137*sx,132*sy,copy_text.get('package_tagline',''),4.2*fs,package_ink,'400',93*sx)
        save(package,'package-front',w,h)
        # 四面与折叠位置的概念布局；深度来自明确需求或已记录假设，不冒充生产刀版。
        depth=pk['depth_mm']; nw,nh=2*w+2*depth,h+2*depth
        net=t.canvas(nw,nh,p['纸面'])
        rect(net,0,depth,w,h,p['朱红'])
        place(net,package,0,depth,w,h,'net-front-')
        area(net,tile,w,depth,depth,h,pk['repeat_width_mm'],'net-side-a')
        rect(net,w+depth,depth,w,h,p['园林青'])
        text(net,w+depth+10,depth+25,b['brand'],min(9,w/20),package_ink,'700',w-20)
        text(net,w+depth+10,depth+43,b['unit_name'],min(6,w/30),package_ink,'400',w-20)
        area(net,tile,w+depth,depth+h*.72,w,h*.28,pk['repeat_width_mm'],'net-back')
        area(net,tile,2*w+depth,depth,depth,h,pk['repeat_width_mm'],'net-side-b')
        for panel_x,panel_w in [(0,w),(w,depth),(w+depth,w),(2*w+depth,depth)]:
            for flap_y in (0,depth+h):
                rect(net,panel_x,flap_y,panel_w,depth,p['纸面'],stroke='#999999',**{'stroke-width':.3})
        for fold_x in (w,w+depth,2*w+depth):
            net.append(t.node('line',{'x1':fold_x,'y1':depth,'x2':fold_x,'y2':depth+h,
                       'stroke':'#777777','stroke-width':.4,'stroke-dasharray':'3 2'}))
        for fold_y in (depth,depth+h):
            net.append(t.node('line',{'x1':0,'y1':fold_y,'x2':nw,'y2':fold_y,
                       'stroke':'#777777','stroke-width':.4,'stroke-dasharray':'3 2'}))
        save(net,'package-layout',nw,nh,'包装四面展开概念；折线为示意，非生产刀版',
             {'depth_mm':depth,'depth_assumed':pk['depth_assumed'],'panel_order':['正面','侧面','背面','侧面'],
              'missing_production_inputs':['已核对刀版','粘口与锁扣','工艺与必要产品信息']})

    def build_fabric():
        # 一至四种可配置面料配色，全部保持母版几何。
        colors=b['colorways'];swatches=t.canvas(900,620,p['纸面'])
        text(swatches,28,46,b['unit_name']+' · 面料配色',26,p['文字'],'700',844)
        spacing=844/len(colors)
        for index,c in enumerate(colors):
            x=28+spacing*index
            v=recolor(tile,{p['轮廓带']:p[c['foreground']],p['负形与背景']:p[c['background']]})
            area(swatches,v,x,85,spacing-20,450,82,f'swatch-{index}')
            text(swatches,x,575,c['name'],18,p['文字'],'700',spacing-20)
            save(v,'fabric-tile-'+str(index+1),status='同结构面料配色重复块')
        save(swatches,'fabric-colorways',status='面料平面配色，非产品照片')

    def build_magnet():
        # 区分自由摆放完整单元与四块还原同一图案，不以四枚卡片冒充可连缀结构。
        ms=b['applications']['magnet'];mw,mh=ms['width_mm'],ms['height_mm'];dw,dh=mw*6,mh*3.2
        magnets=t.canvas(dw,dh,p['纸面'])
        text(magnets,mw*.2,mh*.3,b.get('poster_title',b['unit_name'])+' · '+('拆拼还原' if ms['mode']=='connected_quadrants' else '自由摆放'),mh*.16,p['文字'],'700',dw-mw*.4)
        inks=list(dict.fromkeys([p['轮廓带'],p['负形与背景'],p['朱红'],p['园林青']]+[v for k,v in p.items() if k not in ('纸面','文字')]))
        if ms['mode']=='connected_quadrants':
            modules,assembly,reference,module_record=magnet_modules.split(unit,mw,mh,p['负形与背景'])
            save(assembly,'magnet-assembly',2*mw,2*mh,'四块原位拼合图；非实物照片',module_record)
            save(reference,'magnet-assembly-reference',2*mw,2*mh,'同母版整体图，供拆拼还原检查')
        else:
            modules=[]
            for index in range(4):
                ink=inks[index%len(inks)]
                module=t.canvas(mw,mh)
                rect(module,mw*.02,mh*.02,mw*.96,mh*.96,p['纸面'],rx=min(mw,mh)*.05,stroke=ink,**{'stroke-width':min(mw,mh)*.012})
                mono=recolor(unit,{p['轮廓带']:ink})
                place(module,mono,mw*.12,mh*.12,mw*.76,mh*.76,f'module-{index}-')
                modules.append(module)
            module_record={'mode':'motif_tiles','master':'unit-color.svg','master_geometry':t.geometry(unit),
                           'rule':'各枚完整单元自由摆放，不宣称连缀或拼回原型'}
        for index in range(4):
            module=modules[index]
            save(module,'magnet-module-'+str(index+1),mw,mh,'独立磁贴平面概念；实物工艺待核对',
                 {'mode':ms['mode'],'row':index//2,'column':index%2})
            gap=1 if ms['mode']=='connected_quadrants' else 1.02
            place(magnets,module,mw*(.35+(index%2)*gap),mh*(.58+(index//2)*gap),mw,mh,f'combined-{index}-')
            place(magnets,module,mw*(3.52+(index%2)*1.18),mh*(.6+(index//2)*1.15),mw,mh,f'separated-{index}-')
        text(magnets,mw*.4,mh*2.87,'组合',mh*.09,p['文字'],'700')
        text(magnets,mw*3.55,mh*2.87,'拆分',mh*.09,p['文字'],'700')
        text(magnets,mw*.2,mh*3.1,f'独立底板 / 每枚{mw:g}×{mh:g}mm / 实物工艺待核对',mh*.073,p['文字'],'400',dw-mw*.4)
        save(magnets,'magnet-modules',dw,dh,'模块组合平面概念，非冰箱摄影样机')
        run_case.dump(output/'magnet-layout.json',module_record)

    builders={'poster':build_poster,'package':build_package,'fabric':build_fabric,'magnet':build_magnet}
    for name in b['deliverables']:
        builders[name]()
    genes={'id':b.get('case_id','custom-pattern'),'name':b['unit_name'],
           '形态基因':{'features':b['features'],'master':'unit-master.svg','repeat':b['repeat']},
           '色彩基因':{'palette':p,'source':b.get('palette_source','本次需求指定，印刷待核对')},
           '寓意基因':b.get('culture',{'status':'待核查','claim':None}),
           '来源说明':b.get('source_note'),'提取身份':report['extracted_identity']}
    run_case.dump(output/'文化基因卡.json',genes)
    tasks=b.get('prompt_tasks')
    if not tasks:
        jobs=json.loads((SKILL/'assets/prompts/deliverables.json').read_text(encoding='utf-8'))
        tasks=[j['id'] for j in jobs if j['id']!='01-提取线稿' or (profile['source'] is not None and profile['extracted'] is not None)]
    manifest=export_prompts.export(output,output/'跨AI提示词',only=tasks)
    shutil.copyfile(SKILL/'references/service-sop.md',output/'定制服务SOP.md')
    shutil.copyfile(SKILL/'assets/handoff/通用对话入口.txt',output/'通用对话入口.txt')
    shutil.copyfile(SKILL/'references/chat-handoff.md',output/'豆包与其他AI使用说明.md')
    run_case.dump(output/'应用规格.json',{'brief':b,'applications':specs,'image_generation':'本脚本未调用'})
    audit=delivery_audit.audit(output)
    run_case.dump(output/'验收记录.json',audit)
    if audit['status']=='需修正':
        raise ValueError('数字交付检查未通过，具体问题见输出目录的验收记录.json')
    elapsed=round(time.perf_counter()-started,3)
    run_case.dump(output/'交付报告.json',{'case_id':b.get('case_id'),'render':report['render'],'prompts':len(manifest['jobs']),
        'upload_ready':sum(j['ready'] for j in manifest['jobs']),'checks':report['checks'],
        'automatic_audit':audit['status'],'audit_record':'验收记录.json',
        'products':'平面稿已导出；照片级样机需图像工具生成后审图',
        'measured_seconds':elapsed,'timing_scope':'已准备SVG到数字交付；不含照片提取、人工确认或实物制作',
        'files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in output.iterdir() if f.is_file()}})
    notes=[f"# {b['name']} · 数字交付", "",
        "- [单元母版](unit-master.svg)、[彩色单元](unit-color.svg)、[单元线稿](unit-lineart.svg)。",
        "- [彩色连续](repeat-3x3.svg)、[连续线稿](lineart-3x3.svg)、[重复块](tile-color.svg)、[排列配置](layout-color.json)。"]
    notes += [f"- [{s['file']}]({s['file']})：{s['status']}。" for s in specs]
    if 'package' in b['deliverables']:notes.append(b['package_depth_note']+"；展开为概念示意，非生产刀版。")
    if 'magnet' in b['deliverables']:notes.append("磁贴模式："+b['magnet_mode']+"；规则见[组合记录](magnet-layout.json)。")
    notes += ["", "- [跨AI提示词](跨AI提示词/使用说明.md)、[可直接复制的对话指令](通用对话入口.txt)。",
        "- [来源卡](source-card.json)、[文化基因卡](文化基因卡.json)、[可搬移需求](设计需求.json)、[验收记录](验收记录.json)。",
        "", report['extracted_identity']+"。"+b.get('source_note','来源待核查')+"。",
        "", "本次只生成指定应用；上传参考不计作生成成果。源稿、位图预览、生成样机与制作稿分开。",
        "接缝检查："+report['checks']['periodic_render']+"。平面应用须实际看图，照片级样机另生成并审图。其他AI实际复现、文化寓意、实物工艺及用户验收待验证。"]
    notes='\n'.join(notes)+'\n'
    (output/'成果入口.md').write_text(notes,encoding='utf-8')
    return {'output':str(output),'render':report['render'],'prompts':len(manifest['jobs']),
            'upload_ready':sum(j['ready'] for j in manifest['jobs'])}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True);parser.add_argument('--brief')
    parser.add_argument('--vector-only',action='store_true');parser.add_argument('--font',action='append',default=[])
    a=parser.parse_args(argv)
    try:
        print(json.dumps(run(a.output,a.vector_only,a.font,a.brief),ensure_ascii=False));return 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print('错误：'+str(exc),file=sys.stderr);return 2


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8');sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
