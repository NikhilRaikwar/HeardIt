async def aggregate_vote_counts(db, test_id: str) -> list[dict]:
    """Count correct selections and answer choices in MongoDB, by condition."""
    pipeline = [
        {'$match': {'test_id': test_id}},
        {
            '$group': {
                '_id': {
                    'condition': '$assigned_condition',
                    'selected_label': '$selected_label',
                },
                'count': {'$sum': 1},
                'correct': {'$sum': {'$cond': ['$correct', 1, 0]}},
            },
        },
        {'$sort': {'_id.condition': 1, '_id.selected_label': 1}},
    ]
    cursor = await db.heardit_votes.aggregate(pipeline)
    return [row async for row in cursor]
