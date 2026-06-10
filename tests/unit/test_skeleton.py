from src.ui.app import launch_app


def test_launch_app_is_importable() -> None:
    assert callable(launch_app)
