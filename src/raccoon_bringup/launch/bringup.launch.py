"""Top-level Raccoon bring-up. Run the SAME command on both boards:

    ros2 launch raccoon_bringup bringup.launch.py

Each block below is guarded by _include_if_available(), so a package that is not
built on this board is skipped with a log line instead of killing the launch.
That is what lets one launch file serve two different board images.

Packages that are board-specific also pass board='pi' / board='jetson'. Those are
gated on the `board` launch argument, which defaults to the RACCOON_BOARD
environment variable exported from ~/.bashrc on each board. An unset or unknown
value skips the block — again with a log line rather than an error. The argument
can also be set explicitly, which is handy for testing the other board's path
without touching the environment:

    ros2 launch raccoon_bringup bringup.launch.py board:=pi
"""

import os

from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.conditions import LaunchConfigurationEquals, LaunchConfigurationNotEquals
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration

# Name of the launch argument declared below. Referenced by every board gate, so
# it lives in one place.
_BOARD_ARG = 'board'


def _include_if_available(package, launch_file, board=None):
    """Return [IncludeLaunchDescription] if installed here, else [LogInfo].

    Two independent guards, both of which have to pass:
      * the package is installed on this board — checked here, while the launch
        description is being built, because get_package_share_directory() would
        otherwise raise before any condition is ever evaluated;
      * `board` matches the board argument, when `board` is given — checked at
        execution time, so the included file is not even parsed elsewhere.
    """
    try:
        share = get_package_share_directory(package)
    except PackageNotFoundError:
        return [LogInfo(msg=f'[bringup] {package} not installed on this board — skipped.')]

    path = os.path.join(share, 'launch', launch_file)
    if not os.path.exists(path):
        return [LogInfo(msg=f'[bringup] {package} found but {launch_file} is missing — skipped.')]

    if board is None:
        return [IncludeLaunchDescription(PythonLaunchDescriptionSource(path))]

    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(path),
            condition=LaunchConfigurationEquals(_BOARD_ARG, board),
        ),
        # Without this a forgotten or misspelled RACCOON_BOARD would silently
        # drop the node on a board that has the package installed.
        LogInfo(
            condition=LaunchConfigurationNotEquals(_BOARD_ARG, board),
            msg=[f'[bringup] {package} skipped: {_BOARD_ARG}=',
                 LaunchConfiguration(_BOARD_ARG),
                 f" (expected '{board}'). Export RACCOON_BOARD={board} in ~/.bashrc "
                 f'or pass {_BOARD_ARG}:={board}.'],
        ),
    ]


def generate_launch_description():
    actions = []

    # Declared first: the gates below read this value, and launch actions are
    # visited in order. default_value='' on the EnvironmentVariable is what makes
    # an unset RACCOON_BOARD compare false instead of raising a substitution
    # failure and taking the whole launch down.
    actions.append(DeclareLaunchArgument(
        _BOARD_ARG,
        default_value=EnvironmentVariable('RACCOON_BOARD', default_value=''),
        description="Which board this is: 'pi' or 'jetson'. Defaults to $RACCOON_BOARD.",
    ))

    # ---------------------------------------------------------------- BOTH ---
    # Robot model / TF tree. Needed wherever sensor data is interpreted, so it
    # runs on both boards.
    actions += _include_if_available('raccoon_description', 'description.launch.py')

    # ------------------------------------------------- RASPBERRY PI 4B ONLY ---
    # Hardware interface + RPLIDAR A1. These no-op on the Jetson because neither
    # package is built there.
    actions += _include_if_available('raccoon_lidar', 'rplidar.launch.py', board='pi')
    actions += _include_if_available('raccoon_hardware', 'hardware.launch.py')

    # ------------------------------------------- JETSON ORIN NANO ONLY --------
    # OAK-D Lite camera + perception. No-ops on the Pi.
    actions += _include_if_available('raccoon_perception', 'oakd.launch.py')

    # TODO: add nav2 / slam_toolbox / a static Pi<->Jetson TF publisher here
    #       once those exist. Same guarded-include pattern.

    return LaunchDescription(actions)
