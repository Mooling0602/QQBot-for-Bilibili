import tempfile
import unittest
from pathlib import Path

import yaml

from qqbot.core import updater


class UpdaterTests(unittest.TestCase):
    def _write_yaml(self, path: Path, value: dict) -> None:
        path.write_text(
            yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def test_migrate_adds_live_defaults_and_preserves_custom_description(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.yml"
            features_path = root / "features.yml"
            self._write_yaml(config_path, {"dynamic_monitor": True})
            self._write_yaml(
                features_path,
                {
                    "features": {
                        "live_alert": {
                            "description": "自定义直播说明",
                            "enable": True,
                        }
                    }
                },
            )

            self.assertEqual(updater.migrate(config_path, features_path), (True, True))

            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            features = yaml.safe_load(features_path.read_text(encoding="utf-8"))
            live = features["features"]["live_alert"]
            self.assertEqual(config["version"], "0.2.0")
            self.assertFalse(config["live_monitor"])
            self.assertTrue(live["enable"])
            self.assertFalse(live["notify_on_close"])
            self.assertEqual(live["prompt_on_close"], "")
            self.assertEqual(live["description"], "自定义直播说明")
            self.assertTrue((root / "config.yml.bak").exists())
            self.assertTrue((root / "features.yml.bak").exists())

    def test_migrate_updates_the_known_old_live_description(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.yml"
            features_path = root / "features.yml"
            self._write_yaml(config_path, {"version": "0.1.1"})
            self._write_yaml(
                features_path,
                {
                    "features": {
                        "live_alert": {"description": "推送 UP 主开播提醒到本群"}
                    }
                },
            )

            updater.migrate(config_path, features_path)

            features = yaml.safe_load(features_path.read_text(encoding="utf-8"))
            self.assertEqual(
                features["features"]["live_alert"]["description"],
                "推送 UP 主直播事件到本群",
            )

    def test_migrate_is_idempotent_and_keeps_the_first_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.yml"
            features_path = root / "features.yml"
            self._write_yaml(config_path, {"dynamic_monitor": False})
            self._write_yaml(features_path, {"features": {}})
            original_config = config_path.read_text(encoding="utf-8")
            original_features = features_path.read_text(encoding="utf-8")

            self.assertEqual(updater.migrate(config_path, features_path), (True, True))
            self.assertEqual(
                updater.migrate(config_path, features_path), (False, False)
            )

            self.assertEqual(
                (root / "config.yml.bak").read_text(encoding="utf-8"),
                original_config,
            )
            self.assertEqual(
                (root / "features.yml.bak").read_text(encoding="utf-8"),
                original_features,
            )
