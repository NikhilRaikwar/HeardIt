import json
from pathlib import Path
from app.main import app
target = Path(__file__).parent / 'openapi.json'
target.write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')
print(f'Exported {target.name}')
