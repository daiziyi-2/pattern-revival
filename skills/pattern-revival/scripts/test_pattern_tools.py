"""离线行为验证；PNG 像素验证在有 resvg-py 和 Pillow 时额外执行。"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import pattern_tools as tools

HAS_RENDER = importlib.util.find_spec('resvg_py') is not None and importlib.util.find_spec('PIL') is not None


class PatternToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.source = self.folder / 'unit.svg'
        self.source.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
          <g transform="translate(2 3)" style="fill:#123456;stroke:#abcdef;opacity:0.4">
          <path d="M10 10 L80 10 L80 80 Z" stroke-width="4"/>
          <circle cx="30" cy="30" r="5" fill="#123456"/></g></svg>''', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def run_tool(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return tools.main(list(map(str, args)))

    def config(self, unit=None, placements=None, w=100, h=100):
        path = self.folder / 'layout.json'
        path.write_text(json.dumps({'unit': str(unit or self.source), 'tile': {'width': w, 'height': h},
                                   'background': '#ffffff', 'placements': placements or [{'x': 0, 'y': 0}]}), encoding='utf-8')
        return path

    def test_paint_preserves_paths_transforms_and_inline_style_precedence(self):
        out = self.folder / 'paint.svg'
        self.assertEqual(self.run_tool('paint', '--input', self.source, '--map', '#123456=#E84A27', '--output', out), 0)
        a, b = tools.read_svg(self.source), tools.read_svg(out)
        self.assertEqual(tools.geometry(a), tools.geometry(b))
        g = next(el for el in b if tools.tag(el) == 'g')
        self.assertEqual(tools.style(g)['fill'], '#e84a27')
        self.assertEqual(g.get('transform'), 'translate(2 3)')
        self.assertEqual(self.run_tool('compare', '--before', self.source, '--after', out), 0)

    def test_lineart_removes_fill_and_opacity_without_changing_geometry(self):
        out = self.folder / 'line.svg'
        self.assertEqual(self.run_tool('lineart', '--input', self.source, '--stroke-width', '1.5', '--output', out), 0)
        result = tools.read_svg(out)
        self.assertEqual(tools.geometry(tools.read_svg(self.source)), tools.geometry(result))
        for el in result.iter():
            self.assertNotIn('opacity', tools.style(el))
            if tools.tag(el) in tools.SHAPES and el.get('data-role') != 'background':
                self.assertEqual(el.get('fill'), 'none')
                self.assertEqual(el.get('stroke'), '#000000')
                self.assertEqual(el.get('stroke-width'), '1.5')
        record = json.loads(out.with_suffix('.record.json').read_text(encoding='utf-8'))
        self.assertTrue(record['geometry_unchanged'])
        self.assertEqual(record['manual_checks']['seams'], '未检查')

    def test_transparent_lineart_removes_only_tagged_background(self):
        root = tools.read_svg(self.source)
        root.insert(0, tools.node('rect', {'width': 100, 'height': 100, 'fill': '#ffffff', 'data-role': 'background'}))
        self.source.write_bytes(ET.tostring(root))
        out = self.folder / 'transparent.svg'
        self.assertEqual(self.run_tool('lineart', '--input', self.source, '--background', 'none', '--output', out), 0)
        self.assertFalse(any(el.get('data-role') == 'background' for el in tools.read_svg(out).iter()))

    def test_geometry_change_detected(self):
        root = tools.read_svg(self.source)
        next(el for el in root.iter() if tools.tag(el) == 'path').set('d', 'M1 1 L2 2')
        changed = self.folder / 'changed.svg'
        changed.write_bytes(ET.tostring(root))
        self.assertEqual(self.run_tool('compare', '--before', self.source, '--after', changed), 2)

    def test_raster_and_css_rejected_without_output(self):
        for content in [
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><image href="data:image/png;base64,abc"/></svg>',
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><style>.a{fill:red}</style><path class="a" d="M0 0 L1 1"/></svg>'
        ]:
            self.source.write_text(content, encoding='utf-8')
            out = self.folder / 'bad.svg'
            self.assertEqual(self.run_tool('lineart', '--input', self.source, '--output', out), 2)
            self.assertFalse(out.exists())

    def test_overwrite_and_unmatched_color_fail_cleanly(self):
        out = self.folder / 'existing.svg'
        out.write_text('保留', encoding='utf-8')
        self.assertEqual(self.run_tool('lineart', '--input', self.source, '--output', out), 2)
        self.assertEqual(out.read_text(encoding='utf-8'), '保留')
        out2 = self.folder / 'notfound.svg'
        self.assertEqual(self.run_tool('paint', '--input', self.source, '--map', '#ff0000=#00ff00', '--output', out2), 2)
        self.assertFalse(out2.exists())

    def test_staggered_period_config_and_preview_references(self):
        out = self.folder / 'tile.svg'
        cfg = self.config(placements=[{'x': 0, 'y': 0}, {'x': 50, 'y': 80}], h=160)
        self.assertEqual(self.run_tool('compose', '--config', cfg, '--output', out), 0)
        self.assertEqual(tools.viewbox(tools.read_svg(out)), (0, 0, 100, 160))
        record = json.loads(out.with_suffix('.record.json').read_text(encoding='utf-8'))
        self.assertEqual(record['config']['placements'][1]['x'], 50)
        preview = self.folder / 'preview.svg'
        self.assertEqual(self.run_tool('preview', '--input', out, '--output', preview), 0)
        root = tools.read_svg(preview)
        self.assertEqual(tools.viewbox(root), (0, 0, 300, 480))
        self.assertEqual(len([el for el in root if tools.tag(el) == 'svg']), 9)
        self.assertEqual(tools.issues(root), [])

    def test_invalid_period_and_scale_rejected(self):
        self.assertEqual(self.run_tool('compose', '--config', self.config(w=0), '--output', self.folder / 'a.svg'), 2)
        self.assertEqual(self.run_tool('compose', '--config', self.config(placements=[{'scale': -1}]), '--output', self.folder / 'b.svg'), 2)

    @unittest.skipUnless(HAS_RENDER, '缺少可选 PNG 验证依赖')
    def test_periodic_wrap_visible_at_both_edges_and_preview_seam(self):
        import resvg_py
        from PIL import Image
        self.source.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
          <rect x="90" y="40" width="20" height="20" fill="#000000"/></svg>''', encoding='utf-8')
        tile = self.folder / 'tile.svg'
        self.assertEqual(self.run_tool('compose', '--config', self.config(), '--output', tile), 0)
        im = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_path=str(tile), width=100))).convert('RGB')
        self.assertEqual(im.getpixel((5, 50)), (0, 0, 0))
        self.assertEqual(im.getpixel((95, 50)), (0, 0, 0))
        self.assertEqual(im.getpixel((50, 50)), (255, 255, 255))
        preview = self.folder / 'preview.svg'
        self.assertEqual(self.run_tool('preview', '--input', tile, '--output', preview), 0)
        canvas = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_path=str(preview), width=300))).convert('RGB')
        self.assertTrue(all(canvas.getpixel((x, 50)) == (0, 0, 0) for x in range(90, 110)))

    @unittest.skipUnless(HAS_RENDER, '缺少可选 PNG 验证依赖')
    def test_nonzero_viewbox_and_mirror_rotation_positions(self):
        import resvg_py
        from PIL import Image
        self.source.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="10 20 100 100">
          <rect x="20" y="40" width="10" height="10" fill="#000000"/></svg>''', encoding='utf-8')
        tile = self.folder / 'tile.svg'
        cfg = self.config(placements=[{'rotate': 90, 'mirror': 'x'}])
        self.assertEqual(self.run_tool('compose', '--config', cfg, '--output', tile), 0)
        # 归一化后中心(15,25)，水平镜像到(85,25)，中心旋转90°到(75,85)。
        im = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_path=str(tile), width=100))).convert('RGB')
        self.assertEqual(im.getpixel((75, 85)), (0, 0, 0))
        self.assertEqual(im.getpixel((15, 25)), (255, 255, 255))


if __name__ == '__main__':
    unittest.main(verbosity=2)
