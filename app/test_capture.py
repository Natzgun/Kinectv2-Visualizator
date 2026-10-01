"""Pure conversion checks; no camera or desktop required."""

import unittest

import numpy as np

from capture import display_image


class DisplayImageTests(unittest.TestCase):
    def test_bgra_frame_is_displayed_as_rgb_without_modifying_source(self):
        source = np.array([[[10, 20, 30, 255]]], dtype=np.uint8)
        result = display_image("Color", source)
        np.testing.assert_array_equal(result, [[[30, 20, 10]]])
        np.testing.assert_array_equal(source, [[[10, 20, 30, 255]]])

    def test_depth_range_is_clamped_and_invalid_is_black(self):
        source = np.array([[0, 4500, 9000]], dtype=np.float32)
        result = display_image("Depth", source)
        np.testing.assert_array_equal(result[0, :, 0], [0, 255, 255])

    def test_infrared_normalization(self):
        result = display_image("Infrared", np.array([[0, 65535]], dtype=np.float32))
        np.testing.assert_array_equal(result[0, :, 0], [0, 255])

    def test_invalid_color_depth_mapping_is_black(self):
        source = np.array([[-1, 0, 1920 * 1080]], dtype=np.int32)
        result = display_image("Color-depth map", source)
        np.testing.assert_array_equal(result[0, :, 0], [0, 0, 255])


if __name__ == "__main__":
    unittest.main()
