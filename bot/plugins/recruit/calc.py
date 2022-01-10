import itertools

from .data import recruit_data, known_tags
import re

def _rank(operators):
    if any(x[1] == 2 for x in operators):
        return 0
    try:
        min_rarity = min(x[1] for x in operators if x[1] > 0)
        return min_rarity - 2
    except ValueError:
        return 0.5

def calculate_recruit(ocr_result):
    tags = []
    for i in ocr_result:
        if i in known_tags:
            tags.append(i)
        elif '击干员' in i:
            tags.append('狙击干员')
        elif '高级资深' in i:
            tags.append('高级资深干员')
        elif '资深' in i:
            tags.append('资深干员')

    if len(tags) == 5:
        return calculate_tags(tags)
    else:
        return False

def calculate_tags(tags):
    tags = sorted(tags)
    operator_for_tags = {}
    for tag in tags:
        if tag == '高级资深干员':
            operator_for_tags[(tag,)] = [x[:2] for x in recruit_data if x[1] == 5]
        elif tag == '资深干员':
            operator_for_tags[(tag,)] = [x[:2] for x in recruit_data if x[1] == 4]
        else:
            operators = [x[:2] for x in recruit_data if tag in x[2]]
            if len(operators) == 0:
                raise ValueError('未知 tag: ' + tag)
            operator_for_tags[(tag,)] = operators

    for comb2 in itertools.combinations(tags, 2):
        set1 = operator_for_tags[(comb2[0],)]
        set2 = set(operator_for_tags[(comb2[1],)])
        operators = [x for x in set1 if x in set2]
        if len(operators):
            operator_for_tags[comb2] = operators

    for comb3 in itertools.combinations(tags, 3):
        set1 = operator_for_tags[(comb3[0],)]
        set2 = operator_for_tags[(comb3[1],)]
        set3 = set(operator_for_tags[(comb3[2],)])

        operators = [x for x in set1 if x in set2]
        operators = [x for x in operators if x in set3]

        if len(operators):
            operator_for_tags[comb3] = operators

    for tags in operator_for_tags:
        ops = list(operator_for_tags[tags])
        if '高级资深干员' not in tags:
            ops = [op for op in ops if op[1] != 5]
        ops.sort(key=lambda x: x[1], reverse=True)
        operator_for_tags[tags] = ops
    items = list(operator_for_tags.items())
    combs = [(tags, ops, _rank(ops)) for tags, ops in items]
    return sorted(combs, key=lambda x: (x[2], -len(x[1])), reverse=True)
