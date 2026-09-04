"""OAK-D Lite bring-up (Jetson Orin Nano).

Starts the depthai_ros_driver camera and this package's placeholder consumer.
The driver include is guarded: on a board where depthai_ros_driver is not
installed the launch still comes up instead of hard-failing.
"""

import os

from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def _depthai_camera():
    """Include the depthai_ros_driver camera launch, if it is installed."""
    # TODO: confirm the launch file name against the installed driver. On Humble
    #       this is normally:
    #         /opt/ros/humble/share/depthai_ros_driver/launch/camera.launch.py
    #       Some versions ship rgbd_pcl.launch.py / pointcloud.launch.py instead.
    try:
        driver_share = get_package_share_directory('depthai_ros_driver')
    except PackageNotFoundError:
        return [LogInfo(msg='[raccoon_perception] depthai_ros_driver not found — '
                            'camera NOT started (expected off the Jetson).')]

    camera_launch = os.path.join(driver_share, 'launch', 'camera.launch.py')
    if not os.path.exists(camera_launch):
        return [LogInfo(msg=f'[raccoon_perception] {camera_launch} missing — '
                            'camera NOT started. Check the driver version.')]

    return [IncludeLaunchDescription(
        PythonLaunchDescriptionSource(camera_launch),
        # TODO: pass a params_file here to set resolution / fps / enabled streams.
        launch_arguments={}.items(),
    )]


def generate_launch_description():
    perception = Node(
        package='raccoon_perception',
        executable='perception_node',
        name='perception_node',
        output='screen',
    )

    return LaunchDescription(_depthai_camera() + [perception])
