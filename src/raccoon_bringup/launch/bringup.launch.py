"""Top-level Raccoon bring-up. Run the SAME command on both boards:

    ros2 launch raccoon_bringup bringup.launch.py

Each block below is guarded by _include_if_available(), so a package that is not
built on this board is skipped with a log line instead of killing the launch.
That is what lets one launch file serve two different board images.
"""

import os

from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource


def _include_if_available(package, launch_file):
    """Return [IncludeLaunchDescription] if installed here, else [LogInfo]."""
    try:
        share = get_package_share_directory(package)
    except PackageNotFoundError:
        return [LogInfo(msg=f'[bringup] {package} not installed on this board — skipped.')]

    path = os.path.join(share, 'launch', launch_file)
    if not os.path.exists(path):
        return [LogInfo(msg=f'[bringup] {package} found but {launch_file} is missing — skipped.')]

    return [IncludeLaunchDescription(PythonLaunchDescriptionSource(path))]


def generate_launch_description():
    actions = []

    # ---------------------------------------------------------------- BOTH ---
    # Robot model / TF tree. Needed wherever sensor data is interpreted, so it
    # runs on both boards.
    actions += _include_if_available('raccoon_description', 'description.launch.py')

    # ------------------------------------------------- RASPBERRY PI 4B ONLY ---
    # Hardware interface + RPLIDAR A1. These no-op on the Jetson because neither
    # package is built there.
    actions += _include_if_available('raccoon_lidar', 'rplidar.launch.py')
    actions += _include_if_available('raccoon_hardware', 'hardware.launch.py')

    # ------------------------------------------- JETSON ORIN NANO ONLY --------
    # OAK-D Lite camera + perception. No-ops on the Pi.
    actions += _include_if_available('raccoon_perception', 'oakd.launch.py')

    # TODO: add nav2 / slam_toolbox / a static Pi<->Jetson TF publisher here
    #       once those exist. Same guarded-include pattern.

    return LaunchDescription(actions)
