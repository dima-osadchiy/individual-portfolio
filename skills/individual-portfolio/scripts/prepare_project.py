#!/usr/bin/env python3
"""Create editable portfolio brief/config/catalog without overwriting user files."""
import argparse
from pathlib import Path
import sys


def prepare(target):
    assets = Path(__file__).resolve().parents[1] / 'assets'
    mapping = {'brief.md': 'brief.md', 'site.config.json': 'site.config.example.json',
               'catalog.json': 'catalog.example.json'}
    if target.is_symlink():
        raise ValueError('Папка назначения не должна быть символической ссылкой.')
    if target.exists() and not target.is_dir():
        raise ValueError('Назначение должно быть папкой.')
    payloads = {name: (assets / source).read_bytes() for name, source in mapping.items()}
    for name in mapping:
        destination = target / name
        if destination.exists() or destination.is_symlink():
            raise ValueError(f'Файл уже существует, ничего не перезаписано: {destination}')
    target.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        for name, data in payloads.items():
            destination = target / name
            with destination.open('xb') as output:
                created.append(destination)
                output.write(data)
    except Exception:
        for destination in created:
            destination.unlink(missing_ok=True)
        raise
    return created


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path, help='Папка нового или существующего проекта')
    args = parser.parse_args()
    try:
        created = prepare(args.target)
    except (OSError, ValueError) as error:
        print(f'ОШИБКА: {error}', file=sys.stderr)
        return 1
    for path in created:
        print(f'Создан: {path.resolve()}')
    print('Бриф подготовлен. Код сайта создаётся агентом при применении скилла.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
