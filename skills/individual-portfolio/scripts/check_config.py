#!/usr/bin/env python3
"""Check portable portfolio data; this does not test a rendered website."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import urlsplit


def require(condition, message):
    if not condition:
        raise ValueError(message)


def object_(value, label):
    require(isinstance(value, dict), f'{label}: нужен объект.')
    return value


def text_(value, label, filled=False):
    require(isinstance(value, str), f'{label}: нужна строка.')
    require(not filled or bool(value.strip()), f'{label}: заполните значение.')
    return value.strip()


def list_(value, label):
    require(isinstance(value, list), f'{label}: нужен список.')
    return value


def boolean(value, label):
    require(type(value) is bool, f'{label}: нужно true или false.')
    return value


def integer(value, label, minimum, maximum):
    require(type(value) is int and minimum <= value <= maximum,
            f'{label}: нужно целое число от {minimum} до {maximum}.')


def option(value, label, choices):
    text_(value, label)
    require(value in choices, f'{label}: допустимо {", ".join(choices)}.')


def email(value, label):
    require(bool(re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+', value)),
            f'{label}: некорректный email.')


def url(value, label, local=False):
    text_(value, label, True)
    require(not re.search(r'[\s\x00-\x1f\\<>]', value), f'{label}: некорректная ссылка.')
    if local and (value.startswith('#') or (value.startswith('/') and not value.startswith('//'))):
        return
    parsed = urlsplit(value)
    if parsed.scheme in ('http', 'https'):
        require(bool(parsed.hostname) and parsed.username is None and parsed.password is None,
                f'{label}: нужен адрес сайта без учётных данных.')
    elif parsed.scheme == 'mailto':
        email(parsed.path, label)
    elif parsed.scheme == 'tel':
        require(bool(re.fullmatch(r'\+?[0-9() .-]{3,}', parsed.path)), f'{label}: некорректный телефон.')
    else:
        raise ValueError(f'{label}: используйте http, https, mailto или tel.')


def local_file(value, label, root, ready):
    text_(value, label, True)
    path = PurePosixPath(value)
    require(not path.is_absolute() and '..' not in path.parts and
            not re.search(r'[\\:\x00-\x1f?#]', value),
            f'{label}: нужен относительный путь внутри проекта без .. и URL.')
    resolved = (root / path).resolve()
    require(resolved.is_relative_to(root), f'{label}: путь выходит за папку проекта.')
    require(not ready or resolved.is_file(), f'{label}: файл отсутствует ({value}).')


def palette(colors, label):
    colors = object_(colors, label)
    keys = ('background', 'surface', 'text', 'muted', 'accent', 'on_accent', 'border')
    for key in keys:
        value = text_(colors.get(key), f'{label}.{key}')
        require(bool(re.fullmatch(r'#[0-9a-fA-F]{6}', value)), f'{label}.{key}: формат #RRGGBB.')

    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
        return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))

    for foreground, background in (('text', 'background'), ('muted', 'background'),
                                    ('text', 'surface'), ('muted', 'surface'), ('on_accent', 'accent')):
        a, b = sorted((luminance(colors[foreground]), luminance(colors[background])))
        ratio = (b + .05) / (a + .05)
        require(ratio >= 4.5, f'{label}: слабый контраст {foreground}/{background} ({ratio:.2f}:1).')


def validate(root, ready=False):
    root = root.resolve()
    config = object_(json.loads((root / 'site.config.json').read_text(encoding='utf-8')), 'config')
    catalog_data = object_(json.loads((root / 'catalog.json').read_text(encoding='utf-8')), 'catalog')
    for label, data in [('config', config), ('catalog', catalog_data)]:
        require(type(data.get('schema_version')) is int and data['schema_version'] == 1,
                f'{label}: поддерживается schema_version 1.')
    for section in ('identity', 'hero', 'theme', 'layout', 'catalog', 'content', 'pricing', 'contact', 'admin', 'seo'):
        object_(config.get(section), section)
    identity = config['identity']
    for key in ('name', 'specialty', 'audience', 'language', 'site_url'):
        value = text_(identity.get(key), f'identity.{key}', ready and key != 'site_url')
        if key == 'site_url' and value:
            url(value, 'identity.site_url')
            require(urlsplit(value).scheme in ('http', 'https'), 'site_url: нужен URL сайта.')
    hero = config['hero']
    for key in ('headline', 'description', 'cta_label', 'cta_target'):
        text_(hero.get(key), f'hero.{key}', ready)
    if hero['cta_target']:
        url(hero['cta_target'], 'hero.cta_target', local=True)
    theme = config['theme']
    option(theme.get('mode'), 'theme.mode', ('light', 'dark', 'system'))
    text_(theme.get('direction'), 'theme.direction', True)
    palette(theme.get('colors'), 'theme.colors')
    if theme['mode'] == 'system':
        palette(theme.get('dark_colors'), 'theme.dark_colors')
    fonts = object_(theme.get('fonts'), 'theme.fonts')
    for role in ('heading', 'body'):
        font = object_(fonts.get(role), f'fonts.{role}')
        for field in ('family', 'fallback'):
            name = text_(font.get(field), f'fonts.{role}.{field}', True)
            require(not re.search(r'[;{}<>\x00-\x1f]', name), f'fonts.{role}.{field}: недопустимые символы.')
        for file in list_(font.get('files'), f'fonts.{role}.files'):
            local_file(file, f'fonts.{role}.files', root, ready)
    integer(theme.get('radius_px'), 'theme.radius_px', 0, 100)
    integer(theme.get('max_width_px'), 'theme.max_width_px', 640, 2400)
    option(theme.get('density'), 'theme.density', ('airy', 'balanced', 'compact'))
    option(theme.get('motion'), 'theme.motion', ('none', 'subtle', 'expressive'))
    layout = config['layout']
    option(layout.get('hero'), 'layout.hero', ('split', 'work-first', 'statement', 'portrait', 'feature'))
    option(layout.get('navigation'), 'layout.navigation', ('top', 'side', 'compact'))
    option(layout.get('gallery'), 'layout.gallery', ('grid', 'editorial', 'index', 'stack'))
    sections = list_(layout.get('sections'), 'layout.sections')
    for section in sections:
        text_(section, 'layout.sections[]', True)
        require(section in ('hero', 'work', 'about', 'services', 'process', 'pricing', 'proof', 'faq', 'contact'),
                f'Неизвестная секция: {section}')
    require(len(sections) == len(set(sections)), 'Секции не должны повторяться.')
    boolean(layout.get('project_pages'), 'layout.project_pages')
    cat = config['catalog']
    categories = set()
    for category in list_(cat.get('categories'), 'catalog.categories'):
        category = object_(category, 'category')
        category_id = text_(category.get('id'), 'category.id', True)
        require(bool(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', category_id)), 'category.id: используйте slug латиницей.')
        require(category_id not in categories, f'Повторная категория: {category_id}')
        categories.add(category_id)
        text_(category.get('label'), 'category.label', True)
    for key in ('filters', 'search', 'show_captions', 'lightbox'):
        boolean(cat.get(key), f'catalog.{key}')
    option(cat.get('sort'), 'catalog.sort', ('manual', 'newest'))
    option(cat.get('image_fit'), 'catalog.image_fit', ('contain', 'cover'))
    content = config['content']
    text_(content.get('about'), 'content.about')
    for group, fields in [('services', ('title', 'description')), ('process', ('title', 'description')),
                          ('faq', ('question', 'answer'))]:
        for item in list_(content.get(group), f'content.{group}'):
            item = object_(item, group)
            for field in fields:
                text_(item.get(field), f'{group}.{field}', True)
    for item in list_(content.get('proof'), 'content.proof'):
        item = object_(item, 'proof')
        for field in ('title', 'description', 'source'):
            text_(item.get(field), f'proof.{field}', field != 'source')
        if boolean(item.get('verified'), 'proof.verified'):
            text_(item.get('source'), 'proof.source', True)
    pricing = config['pricing']
    option(pricing.get('mode'), 'pricing.mode', ('hidden', 'on-request', 'from', 'packages'))
    text_(pricing.get('currency'), 'pricing.currency')
    packages = list_(pricing.get('packages'), 'pricing.packages')
    require(not ready or pricing['mode'] not in ('from', 'packages') or bool(packages),
            'Заполните pricing.packages для выбранного режима цен.')
    for package in packages:
        package = object_(package, 'pricing.package')
        for field in ('name', 'price', 'description', 'cta_label'):
            text_(package.get(field), f'package.{field}', True)
        for feature in list_(package.get('features'), 'package.features'):
            text_(feature, 'package.features[]', True)
    contact = config['contact']
    option(contact.get('mode'), 'contact.mode', ('links', 'form'))
    address = text_(contact.get('email'), 'contact.email')
    if address:
        email(address, 'contact.email')
    links = list_(contact.get('links'), 'contact.links')
    for link in links:
        link = object_(link, 'contact.link')
        text_(link.get('label'), 'contact.link.label', True)
        url(link.get('url'), 'contact.link.url')
    provider = text_(contact.get('form_provider'), 'contact.form_provider')
    require(not ready or address or links, 'Добавьте контакт владельца: email или ссылку.')
    require(not ready or contact['mode'] != 'form' or provider,
            'Укажите сервис формы; реальная отправка проверяется отдельно.')
    boolean(config['admin'].get('enabled'), 'admin.enabled')
    text_(config['admin'].get('language'), 'admin.language', True)
    for field in ('title', 'description', 'social_image'):
        value = text_(config['seo'].get(field), f'seo.{field}', ready and field != 'social_image')
        if field == 'social_image' and value:
            local_file(value, 'seo.social_image', root, ready)
    identifiers = set()
    works = list_(catalog_data.get('works'), 'catalog.works')
    for raw in works:
        work = object_(raw, 'work')
        identifier = text_(work.get('id'), 'work.id', True)
        require(identifier not in identifiers, f'Повторный work.id: {identifier}')
        identifiers.add(identifier)
        for field in ('title', 'alt', 'description'):
            text_(work.get(field), f'{identifier}.{field}', field != 'description')
        for field in ('published', 'archived', 'demo'):
            boolean(work.get(field), f'{identifier}.{field}')
        public = work['published'] and not work['archived']
        require(not ready or not public or not work['demo'],
                f'{identifier}: демонстрационная работа не готова к публичной публикации.')
        local_file(work.get('image'), f'{identifier}.image', root, ready and public)
        assigned = list_(work.get('categories'), f'{identifier}.categories')
        for category in assigned:
            text_(category, f'{identifier}.categories[]', True)
            require(category in categories, f'{identifier}: неизвестная категория {category}')
        require(len(assigned) == len(set(assigned)), f'{identifier}: категория повторяется.')
        for field in ('width', 'height'):
            integer(work.get(field), f'{identifier}.{field}', 1, 100000)
        integer(work.get('position'), f'{identifier}.position', 0, 1000000)
        integer(work.get('year'), f'{identifier}.year', 1900, 2200)
    return len(works)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--ready', action='store_true', help='Проверить заполненность и публичные файлы')
    args = parser.parse_args()
    try:
        count = validate(args.project, args.ready)
    except (OSError, ValueError, RecursionError) as error:
        print(f'ОШИБКА: {error}', file=sys.stderr)
        return 1
    print(f'OK: данные {"заполнены" if args.ready else "черновика корректны"}; работ: {count}.')
    print('Проверены входные данные. Внешний вид, сервер и отправка формы проверяются отдельно.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
