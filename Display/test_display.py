import json
import time
import unittest
import urllib.request
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Display import display as display_module
from Display.display import manager
from settings import settings


class DisplayManagerTests(unittest.TestCase):
    def test_publish_exposes_latest_state_snapshot(self):
        display = manager(open_browser=False)

        display.publish(42.5, "smile")

        self.assertEqual(
            display.snapshot(),
            {"state": 42.5, "image": "smile", "version": 1},
        )

    def test_local_server_serves_state_and_minimal_frontend(self):
        display = manager(port=0, open_browser=False)
        display.publish(-30, "bored")
        display.start()
        try:
            with urllib.request.urlopen(f"{display.url}/api/state", timeout=2) as response:
                payload = json.load(response)
            with urllib.request.urlopen(display.url, timeout=2) as response:
                html = response.read().decode("utf-8")
            with urllib.request.urlopen(f"{display.url}/style.css", timeout=2) as response:
                css = response.read().decode("utf-8")
            with urllib.request.urlopen(f"{display.url}/app.js", timeout=2) as response:
                javascript = response.read().decode("utf-8")

            self.assertEqual(payload["state"], -30.0)
            self.assertEqual(payload["image"], "bored")
            self.assertIn('id="portrait"', html)
            self.assertNotIn("<p", html)
            self.assertNotIn("<h1", html)
            self.assertIn("background: #000", css)
            self.assertIn("object-fit: contain", css)
            self.assertIn("@keyframes portrait-hop", css)
            self.assertIn("animation: portrait-hop 300ms", css)
            self.assertIn("state.image !== currentImage", javascript)
            self.assertIn('classList.add("portrait-hop")', javascript)
            self.assertIn("animationend", javascript)
        finally:
            display.stop()

    def test_publish_rejects_missing_portrait(self):
        display = manager(open_browser=False)

        with self.assertRaises(ValueError):
            display.publish(0, "does-not-exist")

    def test_robot_state_is_published_with_its_selected_portrait(self):
        class RobotState:
            def state_get(self):
                return 72

            def state_tachie_get(self):
                return "happy"

        published = []

        class Display:
            def publish(self, state, image):
                published.append((state, image))

        result = display_module.publish_robot_state(RobotState(), Display())

        self.assertEqual(result, (72, "happy"))
        self.assertEqual(published, [(72, "happy")])


@unittest.skipUnless(
    os.environ.get("RUN_DISPLAY_EFFECT_TEST") == "1",
    "设置 RUN_DISPLAY_EFFECT_TEST=1 才会运行真实页面切换测试",
)
class RealDisplayEffectTests(unittest.TestCase):
    """Open the real JS frontend and cycle registered portraits every 5 seconds."""

    def test_registered_portraits_change_every_five_seconds(self):
        display = manager(port=0, open_browser=True)
        registered = sorted(
            settings["Visualization_map"].items(),
            key=lambda item: item[1],
        )
        display.start()
        try:
            for portrait_name, state in registered:
                display.publish(state, portrait_name)
                time.sleep(5)
        finally:
            display.stop()


if __name__ == "__main__":
    unittest.main()
