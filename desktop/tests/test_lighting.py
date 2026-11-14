"""Low-light recovery tests with no screen windows or monitor changes."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


class LightingTests(unittest.TestCase):
    def setUp(self):
        self.brightness = Mock()
        self.brightness.get_brightness.return_value = [40]
        spec = importlib.util.spec_from_file_location('lighting_test', Path(__file__).resolve().parents[1] / 'lighting.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'screen_brightness_control': self.brightness}):
            spec.loader.exec_module(self.module)
        with patch.object(self.module, 'FillLight'):
            self.helper = self.module.LowLightHelper()

    def test_room_lights_return_hides_border_and_restores_original_brightness(self):
        self.helper.update(20, 70, 0)
        self.helper.step(20, 1)
        # Normal light is only 20 above the threshold: the old +40 rule got stuck.
        for tick in range(1, 301):
            self.helper.update(90, 70, tick / 30)
        self.assertFalse(self.helper.active)
        self.helper.fill_light.hide.assert_called_once()
        self.brightness.set_brightness.assert_called_with(40)

    def test_one_bright_frame_does_not_remove_border(self):
        self.helper.update(20, 70, 0)
        self.helper.update(255, 70, .1)
        self.helper.update(20, 70, .2)
        self.assertTrue(self.helper.active)
        self.helper.fill_light.hide.assert_not_called()

    def test_recovery_does_not_depend_on_monitor_brightness_support(self):
        self.brightness.get_brightness.side_effect = RuntimeError('unsupported monitor')
        self.helper.update(20, 70, 0)
        for tick in range(1, 301):
            self.helper.update(90, 70, tick / 30)
        self.assertFalse(self.helper.active)
        self.helper.fill_light.hide.assert_called_once()


if __name__ == '__main__':
    unittest.main()
