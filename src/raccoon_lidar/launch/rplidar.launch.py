"""RPLIDAR A1 bring-up (Raspberry Pi 4B).

Parameters live in config/rplidar.yaml; the node name below must stay in sync
with the top-level key in that file.

serial_port is exposed as a launch argument so it can be pointed at a different
device without editing the YAML:

    ros2 launch raccoon_lidar rplidar.launch.py serial_port:=/dev/ttyUSB0
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    params_file = os.path.join(
        get_package_share_directory('raccoon_lidar'), 'config', 'rplidar.yaml'
    )

    # /dev/rplidar is the stable symlink from the Pi's udev rule. The raw
    # /dev/ttyUSB* enumeration order moves as soon as another USB serial device
    # is plugged in first, so it is never the right default.
    serial_port = DeclareLaunchArgument(
        'serial_port',
        default_value='/dev/rplidar',
        description='Serial device for the RPLIDAR A1 (udev symlink, not /dev/ttyUSB*).',
    )

    rplidar = Node(
        package='rplidar_ros',
        executable='rplidar_node',
        name='rplidar_node',
        output='screen',
        # The dict is listed after params_file so the launch argument wins over
        # the serial_port entry in the YAML. Everything else comes from the YAML.
        parameters=[params_file, {'serial_port': LaunchConfiguration('serial_port')}],
    )

    return LaunchDescription([serial_port, rplidar])
