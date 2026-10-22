"""提示词交接包的可搬移性、母版保护与缺失参考降级。"""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
import export_prompts


class PromptDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.case = self.root/'case'; self.case.mkdir()
        source = export_prompts.SKILL/'assets/units/quatrefoil-team-arrangement.svg'
        shutil.copyfile(source, self.case/'repeat-3x3.svg')
        shutil.copyfile(export_prompts.delivery_profile.DEFAULT, self.case/'设计需求.json')
        self.before = (self.case/'repeat-3x3.svg').read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def test_moved_pack_keeps_all_references_and_input(self):
        output = self.root/'prompts'
        manifest = export_prompts.export(self.case, output, only=['09-仅换色'])
        moved = self.root/'another-computer'; shutil.move(output, moved)
        for job in manifest['jobs']:
            self.assertTrue((moved/job['prompt']).is_file())
            for ref in job['references']:
                self.assertFalse(Path(ref['file']).is_absolute())
                self.assertEqual(hashlib.sha256((moved/ref['file']).read_bytes()).hexdigest(), ref['sha256'])
                self.assertFalse(ref['upload_ready'])
        self.assertEqual(self.before, (self.case/'repeat-3x3.svg').read_bytes())
        self.assertFalse(manifest['jobs'][0]['ready'])

    def test_missing_finished_application_is_reported(self):
        manifest = export_prompts.export(self.case, self.root/'prompts', only=['04-品牌海报'])
        job = manifest['jobs'][0]
        self.assertFalse(job['ready'])
        self.assertIn('poster-brand', [r['name'] for r in job['missing_references']])
        self.assertEqual(list(range(1, len(job['references'])+1)), [r['order'] for r in job['references']])

    def test_empty_input_and_unknown_task_do_not_write(self):
        empty = self.root/'empty'; empty.mkdir()
        for case, only in [(empty, ['09-仅换色']), (self.case, ['不存在'])]:
            with self.assertRaises(ValueError):
                export_prompts.export(case, self.root/'prompts', only=only)
            self.assertFalse((self.root/'prompts').exists())

    def test_existing_pack_is_preserved(self):
        output = self.root/'prompts'; output.mkdir()
        keep = output/'用户文件.txt'; keep.write_text('保留', encoding='utf-8')
        with self.assertRaises(ValueError):
            export_prompts.export(self.case, output, only=['09-仅换色'])
        self.assertEqual(keep.read_text(encoding='utf-8'), '保留')
        with self.assertRaises(ValueError):
            export_prompts.export(self.case, self.case, only=['09-仅换色'])

    def test_missing_current_brief_does_not_assume_another_case(self):
        (self.case/'设计需求.json').unlink()
        with self.assertRaisesRegex(ValueError, '本次设计需求'):
            export_prompts.export(self.case,self.root/'prompts',only=['09-仅换色'])
        self.assertFalse((self.root/'prompts').exists())

    def test_optional_product_reference_is_attached_when_available(self):
        first = export_prompts.export(self.case, self.root/'first', only=['06-布包效果'])['jobs'][0]
        self.assertNotIn('bag-product-preview', [r['name'] for r in first['missing_references']])
        shutil.copyfile(self.case/'repeat-3x3.svg', self.case/'bag-product-preview.svg')
        second = export_prompts.export(self.case, self.root/'second', only=['06-布包效果'])['jobs'][0]
        self.assertEqual(len(first['references'])+1, len(second['references']))
        self.assertTrue(any('bag-product-preview' in r['file'] for r in second['references']))


if __name__ == '__main__':
    unittest.main()
