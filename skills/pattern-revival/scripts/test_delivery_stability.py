"""针对实际偏差的行为回归：拆拼还原、参考隔离、旧检查失效与提取身份。"""
import copy
import importlib.util
import io
import json
import unittest
import xml.etree.ElementTree as ET
from unittest import mock
import delivery_profile
import delivery_audit
import export_prompts
import magnet_modules
import pattern_tools as t
import run_delivery
import test_generic_delivery as fixtures

HAS_PIXELS=all(importlib.util.find_spec(m) for m in ('resvg_py','PIL'))


class DeliveryStabilityTests(unittest.TestCase):
    setUp=fixtures.GenericDeliveryTests.setUp
    tearDown=fixtures.GenericDeliveryTests.tearDown
    write_brief=fixtures.GenericDeliveryTests.write_brief
    generate=fixtures.GenericDeliveryTests.generate

    def test_connected_modules_and_moved_assumed_depth(self):
        self.b['applications']['magnet']['mode']='connected_quadrants';self.write_brief()
        out,_=self.generate()
        record=json.loads((out/'magnet-layout.json').read_text(encoding='utf-8'))
        self.assertEqual(record['assembly_size_mm'],[64,80])
        self.assertEqual([m['assembly_position_mm'] for m in record['modules']],[[0,0],[32,0],[0,40],[32,40]])
        for i in range(1,5):
            root=t.read_svg(out/f'magnet-module-{i}.svg')
            self.assertTrue(any(t.tag(el)=='clipPath' for el in root.iter()))
        portable=json.loads((out/'设计需求.json').read_text(encoding='utf-8'))
        self.assertTrue(portable['applications']['package']['depth_assumed'])
        run_delivery.run(self.folder/'rerun',True,brief=out/'设计需求.json')
        rerun=json.loads((self.folder/'rerun/设计需求.json').read_text(encoding='utf-8'))
        self.assertTrue(rerun['applications']['package']['depth_assumed'])
        self.assertEqual(t.geometry(t.read_svg(out/'magnet-assembly.svg')),t.geometry(t.read_svg(self.folder/'rerun/magnet-assembly.svg')))

    @unittest.skipUnless(HAS_PIXELS,'缺少像素依赖')
    def test_split_nonzero_viewbox_restores_whole_picture(self):
        import resvg_py
        from PIL import Image,ImageChops,ImageStat
        unit=t.read_svg(self.unit);before=t.geometry(unit)
        modules,assembly,reference,record=magnet_modules.split(unit,32,40,'#FFFFFF')
        images=[Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=ET.tostring(root,encoding='unicode'),width=600))).convert('RGBA')
                for root in (assembly,reference)]
        self.assertEqual(images[0].size,images[1].size)
        self.assertLess(max(ImageStat.Stat(ImageChops.difference(*images)).mean),.5)
        self.assertEqual(t.geometry(unit),before)

    def test_invalid_module_mode_fails_before_output(self):
        self.b['applications']['magnet']['mode']='imaginary-joints';self.write_brief()
        with self.assertRaises(ValueError):self.generate()
        self.assertFalse((self.folder/'delivery').exists())

    def test_description_comes_from_layout_and_sizes_not_old_template_text(self):
        self.b['repeat']='错误的四瓣旧参数';self.b['sizes']['海报']='999×999毫米';self.write_brief()
        _,data=delivery_profile.read(self.brief)
        self.assertIn('90×105',data['repeat'])
        self.assertIn('180×260',data['sizes']['海报'])

    def test_brand_equal_to_title_does_not_count_as_two_main_titles(self):
        self.b['brand']=self.b['poster_title'];self.write_brief()
        out,_=self.generate();audit=delivery_audit.audit(out)
        self.assertTrue(any(c['name']=='海报主标题仅一次' and c['status']=='通过' for c in audit['automatic_checks']))

    def test_partial_delivery_needs_no_package_and_does_not_emit_it(self):
        self.b['deliverables']=['poster','magnet']
        self.b.pop('package_title');self.b.pop('package_subtitle');self.b.pop('colorways')
        self.b['applications'].pop('package')
        self.b['applications']['magnet'].update({'mode':'connected_quadrants','presentation':'flat'})
        self.write_brief();out,result=self.generate()
        self.assertFalse((out/'package-front.svg').exists())
        self.assertFalse((out/'package-layout.svg').exists())
        self.assertFalse((out/'fabric-colorways.svg').exists())
        manifest=json.loads((out/'跨AI提示词/提示词清单.json').read_text(encoding='utf-8'))
        self.assertEqual({j['id'] for j in manifest['jobs']},{'02-彩色单元','03-连续纹样','04-品牌海报','07-模块磁贴','09-仅换色','10-去色线稿'})
        profile=json.loads((out/'设计需求.json').read_text(encoding='utf-8'))
        self.assertEqual(profile['applications']['magnet']['presentation'],'flat')
        self.assertEqual(delivery_audit.audit(out)['status'],'数字检查完成，人工项目待核对')

    def test_pattern_only_scope_needs_no_application_fields(self):
        self.b['deliverables']=[];self.b['applications']={}
        for key in ('brand','poster_title','poster_subtitle','package_title','package_subtitle','colorways'):
            self.b.pop(key)
        self.write_brief();out,_=self.generate()
        self.assertTrue((out/'repeat-3x3.svg').is_file())
        self.assertFalse((out/'poster-brand.svg').exists())
        self.assertEqual(delivery_audit.audit(out)['status'],'数字检查完成，人工项目待核对')

    def test_source_without_extracted_unit_does_not_offer_extraction(self):
        self.b['inputs']['source_reference']='陌生单元.svg';self.write_brief()
        out,result=self.generate()
        manifest=json.loads((out/'跨AI提示词/提示词清单.json').read_text(encoding='utf-8'))
        self.assertNotIn('01-提取线稿',[j['id'] for j in manifest['jobs']])
        self.assertIn('未执行原型提取',json.loads((out/'source-card.json').read_text(encoding='utf-8'))['extracted_identity'])
        self.b['prompt_tasks']=['01-提取线稿'];self.write_brief()
        with self.assertRaises(ValueError):run_delivery.run(self.folder/'bad',True,brief=self.brief)
        self.assertFalse((self.folder/'bad').exists())

    def test_carrier_photo_is_not_counted_as_generated_work(self):
        from PIL import Image
        Image.new('RGB',(4,4),'white').save(self.folder/'载体.png')
        self.b['product_references']={'bag':'载体.png'};self.write_brief()
        out,_=self.generate()
        manifest=json.loads((out/'跨AI提示词/提示词清单.json').read_text(encoding='utf-8'))
        carrier=[r for j in manifest['jobs'] for r in j['references'] if r['kind']=='carrier']
        self.assertTrue(carrier);self.assertTrue(all(r['is_deliverable'] is False for r in carrier))
        audit=delivery_audit.audit(out)
        self.assertIn('bag-reference.png',[r['file'] for r in audit['inventory']['references']])
        self.assertNotIn('bag-reference.png',[r['file'] for r in audit['inventory']['generated']])

    def test_changed_brand_or_copy_cannot_override_recorded_case(self):
        out,_=self.generate()
        actual=json.loads((out/'设计需求.json').read_text(encoding='utf-8'))
        for key in ('brand','poster_title','package_subtitle'):
            changed=copy.deepcopy(actual);changed[key]='另一个内容'
            path=self.folder/'override.json';path.write_text(json.dumps(changed,ensure_ascii=False),encoding='utf-8')
            with self.assertRaises(ValueError):export_prompts.export(out,self.folder/'bad',path,only=['04-品牌海报'])
        self.assertFalse((self.folder/'bad').exists())

    def test_audit_detects_geometry_edit_and_keeps_manual_checks_pending(self):
        out,_=self.generate()
        root=t.read_svg(out/'unit-color.svg')
        next(el for el in root.iter() if t.tag(el)=='path').set('d','M0 0 L10 10')
        (out/'unit-color.svg').write_bytes(ET.tostring(root))
        audit=delivery_audit.audit(out)
        self.assertEqual(audit['status'],'需修正')
        self.assertTrue(any(c['name']=='单元换色保持几何' and c['status']=='需修正' for c in audit['automatic_checks']))
        self.assertTrue(all(c['status']=='待人工核对' for c in audit['manual_checks']))

    @unittest.skipUnless(HAS_PIXELS,'缺少像素依赖')
    def test_old_seam_report_cannot_pass_after_tile_edit(self):
        out=self.folder/'rendered';run_delivery.run(out,brief=self.brief)
        initial=delivery_audit.audit(out)
        self.assertTrue(any(c['name']=='重复接缝像素检查' and c['status']=='通过' for c in initial['automatic_checks']))
        root=t.read_svg(out/'tile-color.svg')
        next(el for el in root.iter() if t.tag(el)=='path').set('d','M0 0 L10 10')
        (out/'tile-color.svg').write_bytes(ET.tostring(root))
        audit=delivery_audit.audit(out)
        self.assertTrue(any(c['name']=='重复接缝像素检查' and c['status']=='需修正' for c in audit['automatic_checks']))

    @unittest.skipUnless(HAS_PIXELS,'缺少像素依赖')
    def test_colored_unit_preview_uses_requested_ground_and_lineart_stays_white(self):
        from PIL import Image
        out=self.folder/'rendered';run_delivery.run(out,brief=self.brief)
        color=t.color(self.b['palette']['负形与背景'])
        expected=tuple(int(color[i:i+2],16) for i in (1,3,5))
        self.assertEqual(Image.open(out/'unit-color.png').convert('RGB').getpixel((0,0)),expected)
        self.assertEqual(Image.open(out/'unit-lineart.png').convert('RGB').getpixel((0,0)),(255,255,255))


if __name__=='__main__':unittest.main()
