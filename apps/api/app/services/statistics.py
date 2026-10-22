def wilson(successes: int, sample_size: int, z: float = 1.959963984540054) -> list[float] | None:
    if sample_size == 0:
        return None
    proportion = successes / sample_size
    denominator = 1 + z * z / sample_size
    center = (proportion + z * z / (2 * sample_size)) / denominator
    margin = z * ((proportion * (1 - proportion) / sample_size + z * z / (4 * sample_size * sample_size)) ** 0.5) / denominator
    return [max(0, center - margin), min(1, center + margin)]


def group_from_aggregates(condition: str, labels: list[str], rows: list[dict]) -> dict:
    distribution = {label: 0 for label in labels}
    canonical_labels = {label.casefold(): label for label in labels}
    count = correct = 0
    for row in rows:
        key = row['_id']
        if key['condition'] != condition:
            continue
        label = canonical_labels.get(str(key['selected_label']).casefold())
        if label is not None:
            distribution[label] += row['count']
        count += row['count']
        correct += row['correct']
    return {
        'n': count,
        'correct': correct,
        'rate': correct / count if count else None,
        'interval': wilson(correct, count),
        'distribution': distribution,
    }


def results_from_aggregates(test_id: str, intended_label: str, labels: list[str], rows: list[dict]) -> dict:
    audio = group_from_aggregates('audio', labels, rows)
    text = group_from_aggregates('text', labels, rows)
    total = audio['n'] + text['n']
    return {
        'id': test_id,
        'intended_label': intended_label,
        'labels': labels,
        'total': total,
        'audio': audio,
        'text': text,
        'voice_lift': audio['rate'] - text['rate'] if audio['rate'] is not None and text['rate'] is not None else None,
        'preliminary': total < 20,
        'interpretation': 'Exploratory randomized sample; this difference is not proof of a universal voice effect.',
    }
