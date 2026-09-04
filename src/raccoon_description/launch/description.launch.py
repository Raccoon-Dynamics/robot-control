"""Publish the Raccoon URDF via robot_state_publisher.

Included by raccoon_bringup on BOTH boards — the TF tree has to exist wherever
sensor data is consumed.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.substitutions import Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    pkg_share = get_package_share_directory('raccoon_description')
    xacro_file = os.path.join(pkg_share, 'urdf', 'raccoon.urdf.xacro')

    # ParameterValue(..., value_type=str) keeps the expanded XML from being
    # parsed as YAML, which is the usual "robot_description is empty" bug.
    robot_description = ParameterValue(
        Command(['xacro ', xacro_file]),
        value_type=str,
    )

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_description}],
    )

    # TODO: once real (non-fixed) joints exist, add joint_state_publisher here —
    # or better, let the hardware node publish /joint_states itself.

    return LaunchDescription([robot_state_publisher])
