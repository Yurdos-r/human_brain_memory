import importlib.util
import json
import sys
import zipfile
from pathlib import Path

from human_brain_memory import MemoryConfig

ROOT = Path(__file__).resolve().parents[1]


def test_config_schema_defaults_match_core():
    schema = json.loads((ROOT/'_conf_schema.json').read_text(encoding='utf-8'))
    values = {key: item['default'] for key, item in schema.items()}
    assert MemoryConfig.from_mapping(values) == MemoryConfig()
    assert values['record_all_messages'] is False
    assert values['embedding_provider_id'] == ''


def test_package_allowlist_and_manifest(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('hbm_packager', ROOT/'scripts/package_release.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # Prepare a representative release tree without ever placing a pretend secret in real source.
    for name in mod.FILES:
        p = tmp_path/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{}' if p.suffix == '.json' else 'source', encoding='utf-8')
    (tmp_path/'human_brain_memory').mkdir()
    (tmp_path/'human_brain_memory/engine.py').write_text('x = 1', encoding='utf-8')
    (tmp_path/'data').mkdir()
    (tmp_path/'data/private.sqlite3').write_text('private', encoding='utf-8')
    (tmp_path/'.env').write_text('secret', encoding='utf-8')
    monkeypatch.setattr(mod, 'ROOT', tmp_path)
    archive = mod.package()
    with zipfile.ZipFile(archive) as z:
        paths = z.namelist()
        assert all(p.startswith(mod.PLUGIN+'/') for p in paths)
        assert not any('private.sqlite3' in p or p.endswith('/.env') for p in paths)
        manifest = json.loads(z.read(mod.PLUGIN+'/MANIFEST.sha256.json'))
        assert 'main.py' in manifest and 'human_brain_memory/engine.py' in manifest


def test_core_does_not_import_astrbot():
    # The independent core must stay usable outside the host, including without its SDK dependencies.
    import subprocess
    result = subprocess.run([sys.executable, '-c',
                             'import sys; import human_brain_memory; assert "astrbot" not in sys.modules'],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
