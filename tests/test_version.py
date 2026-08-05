import os
import unittest
from unittest.mock import patch

from qqbot.core import version


class VersionStatusTests(unittest.TestCase):
    def test_release_image_with_matching_tag_is_stable(self) -> None:
        with (
            patch.object(version, "get_base_version", return_value="0.1.1"),
            patch.object(version, "_git_commit", return_value=None),
            patch.dict(os.environ, {"QQBOT_RELEASE_TAG": "0.1.1"}),
        ):
            self.assertEqual(version.get_status_version(), "v0.1.1 (stable)")

    def test_release_image_with_missing_or_wrong_tag_is_git(self) -> None:
        with (
            patch.object(version, "get_base_version", return_value="0.1.1"),
            patch.object(version, "_git_commit", return_value=None),
            patch.dict(os.environ, {"QQBOT_RELEASE_TAG": "0.1.0"}),
        ):
            self.assertEqual(version.get_status_version(), "v0.1.1 (git)")

    def test_source_checkout_always_includes_the_commit_hash(self) -> None:
        with (
            patch.object(version, "get_base_version", return_value="0.1.1"),
            patch.object(version, "_git_commit", return_value="1da4266"),
            patch.dict(os.environ, {"QQBOT_RELEASE_TAG": "0.1.1"}),
        ):
            self.assertEqual(version.get_status_version(), "v0.1.1 (git: 1da4266)")


if __name__ == "__main__":
    unittest.main()
