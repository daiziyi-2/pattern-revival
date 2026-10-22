"""独立外部SVG、实际应用尺寸、跨案例隔离和搬移后重跑的行为测试。"""
import hashlib
import json
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
import delivery_profile
import run_delivery
import export_prompts
import pattern_tools as t


class GenericDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.unit=self.folder/'陌生单元.svg'
        self.unit.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-10 5 80 90">'
            '<g style="fill:none;stroke:#315b74;stroke-width:3"><path d="M0 20 L35 8 L62 30 L58 70 L20 85 L0 55 Z"/>'
            '<path d="M12 25 L48 25 L48 57 L20 67"/></g></svg>',encoding='utf-8')
        self.before=self.unit.read_bytes()
        self.b=json.loads(delivery_profile.DEFAULT.read_text(encoding='utf-8'))
        self.b.update({'case_id':'external-line-test','name':'外部折纹测试','unit_name':'折线实验单元',
            'brand':'测试园','poster_title':'折纹测试','poster_subtitle':'保留折线，进入日常',
            'features':['六边折线外框','独立内部折线'],'inputs':{'unit':'陌生单元.svg'},
            'unit_color_roles':{'#315b74':'轮廓带'},'layout':{'tile':{'width':90,'height':105},'placements':[{'x':3,'y':4}]},
            'brand_assets':{},'product_references':{},'source_note':'测试用独立SVG，不是文化原型提取',
            'prompt_rules':{'unit':'保留两条实际路径','lineart':'保留外框和内部折线','extraction_target':'无需照片提取'},
            'copy':{'series':'折线实验系列','poster_footer':'结构保持测试','package_tagline':'折线测试'}})
        self.b['palette']['轮廓带']='#ABCDEF'
        self.b['applications']['poster'].update({'width_mm':180,'height_mm':260})
        self.b['applications']['package'].update({'width_mm':200,'height_mm':120})
        self.b['applications']['magnet'].update({'width_mm':32,'height_mm':40})
        self.brief=self.folder/'需求.json';self.write_brief()

    def write_brief(self):
        self.brief.write_text(json.dumps(self.b,ensure_ascii=False),encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def generate(self):
        output=self.folder/'delivery'
        result=run_delivery.run(output,vector_only=True,brief=self.brief)
        return output,result

    def test_external_unit_preserves_structure_without_builtin_brand_or_pattern(self):
        out,result=self.generate()
        self.assertEqual(result['prompts'],10)
        self.assertEqual(self.unit.read_bytes(),self.before)
        original=t.read_svg(self.unit);colored=t.read_svg(out/'unit-color.svg')
        self.assertEqual(t.geometry(original),t.geometry(colored))
        self.assertFalse((out/'brand-symbol.svg').exists())
        self.assertFalse((out/'bag-reference.jpg').exists())
        manifest=json.loads((out/'跨AI提示词/提示词清单.json').read_text(encoding='utf-8'))
        for job in manifest['jobs']:
            text=(out/'跨AI提示词'/job['prompt']).read_text(encoding='utf-8')
            self.assertNotIn('四瓣',text)
            for ref in job['references']:
                data=(out/'跨AI提示词'/ref['file']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),ref['sha256'])
        source=json.loads((out/'source-card.json').read_text(encoding='utf-8'))
        self.assertIn('未执行原型提取',source['extracted_identity'])

    def test_actual_sizes_and_one_main_title(self):
        out,_=self.generate()
        for filename,w,h in [('poster-brand.svg','180mm','260mm'),('package-front.svg','200mm','120mm'),('magnet-module-1.svg','32mm','40mm')]:
            root=ET.parse(out/filename).getroot()
            self.assertEqual(root.get('width'),w);self.assertEqual(root.get('height'),h)
        poster=ET.parse(out/'poster-brand.svg').getroot()
        self.assertEqual(sum(el.text=='折纹测试' for el in poster.iter() if t.tag(el)=='text'),1)
        profile=json.loads((out/'设计需求.json').read_text(encoding='utf-8'))
        self.assertIn('180×260',profile['sizes']['海报'])
        self.assertIn('90×105',profile['repeat'])

    def test_moved_delivery_can_be_reexecuted_without_original_machine_paths(self):
        out,_=self.generate();moved=self.folder/'moved';shutil.move(out,moved)
        result=run_delivery.run(self.folder/'rerun',vector_only=True,brief=moved/'设计需求.json')
        self.assertEqual(result['prompts'],10)
        self.assertEqual(t.geometry(t.read_svg(moved/'unit-color.svg')),t.geometry(t.read_svg(self.folder/'rerun/unit-color.svg')))
        self.assertEqual(self.unit.read_bytes(),self.before)

    def test_bad_source_map_and_size_fail_before_writing(self):
        out=self.folder/'bad'
        self.b['unit_color_roles']={'#000001':'轮廓带'};self.write_brief()
        with self.assertRaises(ValueError):run_delivery.run(out,True,brief=self.brief)
        self.assertFalse(out.exists())
        self.b['unit_color_roles']={'#315b74':'轮廓带'}
        self.b['applications']['poster']['width_mm']=0;self.write_brief()
        with self.assertRaises(ValueError):run_delivery.run(out,True,brief=self.brief)
        self.assertFalse(out.exists());self.assertEqual(self.unit.read_bytes(),self.before)

    def test_prompt_export_rejects_wrong_case_and_false_colors(self):
        out,_=self.generate()
        override=json.loads((out/'设计需求.json').read_text(encoding='utf-8'))
        for key,value in [('unit_name','另一个单元'),('palette',{**override['palette'],'轮廓带':'#000001'})]:
            wrong={**override,key:value};path=self.folder/'wrong.json'
            path.write_text(json.dumps(wrong,ensure_ascii=False),encoding='utf-8')
            with self.assertRaises(ValueError):export_prompts.export(out,self.folder/'bad-prompts',path,only=['09-仅换色'])
            self.assertFalse((self.folder/'bad-prompts').exists())

    def test_missing_reference_does_not_borrow_builtin_case(self):
        case=self.folder/'case';case.mkdir();shutil.copyfile(self.unit,case/'repeat-3x3.svg')
        result=export_prompts.export(case,self.folder/'prompts',brief=self.brief,only=['04-品牌海报'])
        job=result['jobs'][0]
        self.assertEqual(len(job['references']),1)
        self.assertIn('poster-brand',[r['name'] for r in job['missing_references']])
        self.assertFalse(job['ready'])


if __name__=='__main__':unittest.main()
