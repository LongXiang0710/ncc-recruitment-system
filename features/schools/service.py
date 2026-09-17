"""院校省市数据规范化规则。"""
import re


def normalize_location(payload, locations):
    province = str(payload.get('province') or '').strip()
    aliases = {re.sub(r'(省|市|壮族自治区|回族自治区|维吾尔自治区|自治区|特别行政区)$', '', name): name for name in locations}
    province = aliases.get(province, province)
    if province not in locations:
        raise ValueError('请选择有效的所在省')
    city = str(payload.get('city') or '').strip()
    if city and city not in locations[province]:
        raise ValueError('所在市不属于所选省份，请重新选择')
    result = dict(payload, province=province, city=city)
    result['province_city'] = ' '.join(str(result.get(key) or '').strip() for key in ('province', 'city') if result.get(key))
    return result

