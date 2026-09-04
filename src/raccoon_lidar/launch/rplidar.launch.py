"""RPLIDAR A1 bring-up (Raspberry Pi 4B).

Parameters live in config/rplidar.yaml; the node name below must stay in sync
with the top-level key in that file.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    params_file = os.path.join(
        get_package_share_directory('raccoon_lidar'), 'config', 'rplidar.yaml'
    )

    rplidar = Node(
        package='rplidar_ros',
        executable='rplidar_node',
        name='rplidar_node',
        output='screen',
        parameters=[params_file],
    )

    return LaunchDescription([rplidar])
