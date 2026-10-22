"""Behavior checks for the portable project preparation and data validation helpers."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/individual-portfolio/scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load('prepare_project').prepare
validate = load('check_config').validate


class HelpersTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / 'project'
        prepare(self.project)
        self.config = json.loads((self.project / 'site.config.json').read_text())
        self.catalog = {'schema_version': 1, 'works': []}

    def save(self):
        (self.project / 'site.config.json').write_text(json.dumps(self.config), encoding='utf-8')
        (self.project / 'catalog.json').write_text(json.dumps(self.catalog), encoding='utf-8')

    def ready_data(self):
        self.config['identity'].update(name='Test Author', specialty='Design', audience='Creators')
        self.config['hero'].update(headline='Selected work', description='Projects and process')
        self.config['seo'].update(title='Test portfolio', description='Selected projects')
        self.config['contact']['email'] = 'author@example.com'

    def work(self):
        self.config['catalog']['categories'] = [{'id': 'covers', 'label': 'Обложки'}]
        return {'id': 'one', 'title': 'Test', 'alt': 'Test image', 'description': '',
                'categories': ['covers'], 'image': 'assets/media/one.svg',
                'width': 100, 'height': 100, 'year': 2026, 'position': 0,
                'published': True, 'archived': False, 'demo': False}

    def test_draft_is_valid_but_not_ready(self):
        self.assertEqual(validate(self.project), 0)
        with self.assertRaises(ValueError):
            validate(self.project, ready=True)

    def test_existing_project_files_are_preserved(self):
        (self.project / 'brief.md').write_text('User edits', encoding='utf-8')
        before = {p.name: p.read_bytes() for p in self.project.iterdir()}
        with self.assertRaises(ValueError):
            prepare(self.project)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.project.iterdir()})

    def test_partial_conflict_creates_no_new_files(self):
        target = Path(self.temporary.name) / 'existing'
        target.mkdir()
        (target / 'catalog.json').write_text('KEEP', encoding='utf-8')
        with self.assertRaises(ValueError):
            prepare(target)
        self.assertEqual([p.name for p in target.iterdir()], ['catalog.json'])

    def test_ready_project_with_public_work(self):
        self.ready_data()
        self.catalog['works'] = [self.work()]
        media = self.project / 'assets/media/one.svg'
        media.parent.mkdir(parents=True)
        media.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>')
        self.save()
        self.assertEqual(validate(self.project, ready=True), 1)

    def test_missing_public_image_is_not_ready(self):
        self.ready_data()
        self.catalog['works'] = [self.work()]
        self.save()
        with self.assertRaisesRegex(ValueError, 'файл отсутствует'):
            validate(self.project, ready=True)

    def test_unknown_category_is_rejected(self):
        work = self.work()
        work['categories'] = ['missing']
        self.catalog['works'] = [work]
        self.save()
        with self.assertRaisesRegex(ValueError, 'неизвестная категория'):
            validate(self.project)

    def test_file_cannot_escape_project(self):
        work = self.work()
        work['image'] = '../private.svg'
        self.catalog['works'] = [work]
        self.save()
        with self.assertRaises(ValueError):
            validate(self.project)

    def test_symlink_cannot_escape_project(self):
        work = self.work()
        external = Path(self.temporary.name) / 'external.svg'
        external.write_text('private')
        (self.project / 'outside.svg').symlink_to(external)
        work['image'] = 'outside.svg'
        self.catalog['works'] = [work]
        self.save()
        with self.assertRaisesRegex(ValueError, 'выходит за папку'):
            validate(self.project)

    def test_unreadable_palette_is_rejected(self):
        self.config['theme']['colors']['text'] = self.config['theme']['colors']['background']
        self.save()
        with self.assertRaisesRegex(ValueError, 'контраст'):
            validate(self.project)

    def test_system_theme_requires_second_palette(self):
        self.config['theme']['mode'] = 'system'
        self.save()
        with self.assertRaisesRegex(ValueError, 'dark_colors'):
            validate(self.project)
        self.config['theme']['dark_colors'] = dict(self.config['theme']['colors'])
        self.save()
        self.assertEqual(validate(self.project), 0)

    def test_demo_work_cannot_pass_as_ready_public_work(self):
        self.ready_data()
        work = self.work()
        work['demo'] = True
        self.catalog['works'] = [work]
        self.save()
        with self.assertRaisesRegex(ValueError, 'демонстрационная работа'):
            validate(self.project, ready=True)

    def test_verified_claim_requires_source(self):
        self.config['content']['proof'] = [{'title': 'Test claim', 'description': 'Test',
                                          'verified': True, 'source': ''}]
        self.save()
        with self.assertRaisesRegex(ValueError, 'source'):
            validate(self.project)

    def test_inactive_work_does_not_need_public_file(self):
        self.ready_data()
        work = self.work()
        work['published'] = False
        self.catalog['works'] = [work]
        self.save()
        self.assertEqual(validate(self.project, ready=True), 1)

    def test_executable_contact_url_is_rejected(self):
        self.config['contact']['links'] = [{'label': 'Contact', 'url': 'javascript:alert(1)'}]
        self.save()
        with self.assertRaises(ValueError):
            validate(self.project)


if __name__ == '__main__':
    unittest.main()
