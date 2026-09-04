"""Bring up the Pi's hardware interface node."""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    hardware = Node(
        package='raccoon_hardware',
        executable='hardware_node',
        name='hardware_node',
        output='screen',
        # TODO: load raccoon_bringup/config/params.yaml here once the node has
        #       real parameters (serial port, wheel radius, gear ratio, ...).
    )

    return LaunchDescription([hardware])
