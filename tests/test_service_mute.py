import unittest

from qqbot.core import service_mute


class ServiceMuteTests(unittest.TestCase):
    def setUp(self) -> None:
        service_mute._MUTED_GROUPS.clear()

    def test_mute_is_limited_to_the_requesting_group(self) -> None:
        service_mute.mute_group("1")

        self.assertTrue(service_mute.is_group_muted("1"))
        self.assertFalse(service_mute.is_group_muted("2"))

        service_mute.resume_group("1")

        self.assertFalse(service_mute.is_group_muted("1"))


if __name__ == "__main__":
    unittest.main()
