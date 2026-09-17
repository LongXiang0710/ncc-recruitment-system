"""Generate the offline school province/city selector from vendored data."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'web'
source = json.loads((root / 'china-areas-source.json').read_text(encoding='utf-8'))
extra = json.loads((root / 'china-areas-extra-source.json').read_text(encoding='utf-8'))
locations = {}
for province, children in source.items():
    if province in ('北京市', '天津市', '上海市', '重庆市'):
        locations[province] = [province]
        continue
    cities = []
    for city, areas in children.items():
        cities.extend(areas if city.endswith('直辖县级行政区划') else [city])
    locations[province] = cities
for province, children in extra.items():
    locations[province] = list(children) if province == '台湾省' else [province.removesuffix('特别行政区')]
(root / 'china-locations.json').write_text(json.dumps(locations, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'Generated {len(locations)} province entries.')
