"""实际源路径与离线案例的行为验证，不调用生成接口。"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import pattern_tools as tools
import export_unit
import apply_pattern
import run_case

HAS_PIXELS = all(importlib.util.find_spec(m) is not None for m in ('resvg_py', 'PIL'))
HAS_SOURCE = HAS_PIXELS and importlib.util.find_spec('pymupdf') is not None
SKILL = Path(__file__).resolve().parents[1]
WORKSPACE = SKILL.parents[2]


class CaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return tools.main(list(map(str, args)))

    def fixture(self):
        unit = self.folder/'unit.svg'
        unit.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                        '<path d="M-10 50 L110 50 M50 -10 L50 110" fill="none" stroke="#000000" stroke-width="8"/></svg>', encoding='utf-8')
        cfg = self.folder/'layout.json'
        cfg.write_text(json.dumps({'unit': 'unit.svg', 'background': '#ffffff',
                                   'tile': {'width': 100, 'height': 100}, 'placements': [{}]}), encoding='utf-8')
        tile = self.folder/'tile.svg'
        self.assertEqual(self.call('compose', '--config', cfg, '--output', tile), 0)
        return cfg, tile

    @unittest.skipUnless(HAS_PIXELS, '缺少像素验证依赖')
    def test_seams_pass_and_detect_missing_connection_and_color_jump(self):
        cfg, tile = self.fixture()
        self.assertEqual(self.call('check-seams', '--config', cfg, '--input', tile,
                                   '--tile-pixels', 128, '--output', self.folder/'good.json'), 0)
        root = tools.read_svg(tile)
        for el in root.iter():
            if tools.tag(el) == 'path':
                el.set('d', 'M10 50 L90 50 M50 10 L50 90')
        bad = self.folder/'broken.svg'; bad.write_bytes(ET.tostring(root))
        self.assertEqual(self.call('check-seams', '--config', cfg, '--input', bad,
                                   '--tile-pixels', 128, '--output', self.folder/'broken.json'), 2)
        root = tools.read_svg(tile)
        next(el for el in root.iter() if tools.tag(el) == 'path').set('stroke', '#ff0000')
        changed = self.folder/'wrong-color.svg'; changed.write_bytes(ET.tostring(root))
        self.assertEqual(self.call('check-seams', '--config', cfg, '--input', changed,
                                   '--tile-pixels', 128, '--output', self.folder/'color.json'), 2)

    @unittest.skipUnless(HAS_PIXELS, '缺少像素验证依赖')
    def test_real_staggered_unit_passes_periodic_render_check(self):
        cfg = SKILL/'assets'/'layouts'/'quatrefoil-team-stagger.json'
        tile = self.folder/'tile.svg'
        self.assertEqual(self.call('compose', '--config', cfg, '--output', tile), 0)
        self.assertEqual(self.call('check-seams', '--config', cfg, '--input', tile,
                                   '--output', self.folder/'seams.json'), 0)

    def test_source_and_unit_overwrite_rejected_even_with_flag(self):
        cfg, tile = self.fixture()
        before = tile.read_bytes()
        self.assertEqual(self.call('lineart', '--input', tile, '--output', tile, '--overwrite'), 2)
        self.assertEqual(tile.read_bytes(), before)
        unit = self.folder/'unit.svg'; before = unit.read_bytes()
        self.assertEqual(self.call('compose', '--config', cfg, '--output', unit, '--overwrite'), 2)
        self.assertEqual(unit.read_bytes(), before)

    def test_application_physical_scale_and_master_are_preserved(self):
        cfg, tile = self.fixture(); before = tile.read_bytes()
        root, record = apply_pattern.application(tile, SKILL/'assets'/'layouts'/'poster-quatrefoil.json')
        self.assertEqual(root.get('width'), '297mm')
        self.assertEqual(root.get('height'), '420mm')
        self.assertEqual(record['scale_mm_per_source_unit'], .42)
        self.assertEqual(tile.read_bytes(), before)
        self.assertTrue(any(tools.tag(el) == 'text' and el.text == '凭窗' for el in root.iter()))
        self.assertFalse(any(tools.tag(el) == 'image' for el in root.iter()))

    def test_offline_vector_chain_without_renderer_or_generation(self):
        out = self.folder/'delivery'
        with mock.patch('run_case.importlib.util.find_spec', side_effect=AssertionError('矢量模式不应探测渲染器')):
            result = run_case.run(out, vector_only=True)
        self.assertEqual(result['checks']['lineart_geometry'], '通过')
        self.assertEqual(result['checks']['cultural_origin'], '待核查')
        self.assertIn('未检查', result['checks']['periodic_render'])
        self.assertTrue((out/'poster.svg').exists())
        self.assertTrue((out/'sleeve-concept.svg').exists())
        self.assertFalse((out/'poster.png').exists())
        self.assertEqual(tools.geometry(tools.read_svg(out/'tile-color.svg')),
                         tools.geometry(tools.read_svg(out/'tile-lineart.svg')))
        with self.assertRaises(ValueError):
            run_case.run(out, vector_only=True)

    @unittest.skipUnless(HAS_SOURCE and (WORKSPACE/'纹样提取(1).ai').exists(), '实际源文件或渲染依赖不可用')
    def test_exported_extraction_matches_source_pixels_and_keeps_clip(self):
        import pymupdf
        import resvg_py
        from PIL import Image, ImageChops, ImageStat
        target = self.folder/'unit.svg'
        with contextlib.redirect_stdout(io.StringIO()):
            export_unit.export(WORKSPACE/'纹样提取(1).ai', SKILL/'assets'/'cases'/'quatrefoil-extraction-selection.json', target)
        root = tools.read_svg(target)
        self.assertTrue(any(tools.tag(el) == 'clipPath' for el in root.iter()))
        vx, vy, w, h = tools.viewbox(root)
        import math
        bounds = pymupdf.Rect(math.floor(vx), math.floor(vy), math.ceil(vx+w), math.ceil(vy+h))
        root.set('viewBox', f'{bounds.x0} {bounds.y0} {bounds.width} {bounds.height}')
        root.set('width', str(bounds.width)); root.set('height', str(bounds.height))
        png = resvg_py.svg_to_bytes(svg_string=ET.tostring(root, encoding='unicode'), width=int(bounds.width*4), background='white')
        actual = Image.open(io.BytesIO(png)).convert('RGB')
        with pymupdf.open(WORKSPACE/'纹样提取(1).ai') as doc:
            pix = doc[1].get_pixmap(matrix=pymupdf.Matrix(4, 4), clip=bounds, alpha=False)
            expected = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        self.assertEqual(actual.size, expected.size)
        # 不同引擎在边缘抗锯齿略有差异，但漏图、补错路径或丢裁切会明显超过此平均差。
        self.assertLess(max(ImageStat.Stat(ImageChops.difference(actual, expected)).mean), 2)
        spec = json.loads((SKILL/'assets'/'cases'/'quatrefoil-extraction-selection.json').read_text(encoding='utf-8'))
        spec['source_sha256'] = '0'*64
        selection = self.folder/'wrong-selection.json'; selection.write_text(json.dumps(spec), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '指纹'):
            export_unit.export(WORKSPACE/'纹样提取(1).ai', selection, self.folder/'wrong.svg')
        self.assertFalse((self.folder/'wrong.svg').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
