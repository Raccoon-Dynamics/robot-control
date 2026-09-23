import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'raccoon_watchdog'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Adam Zhang',
    maintainer_email='reachadamzhang@gmail.com',
    description='Raccoon Watchdog is a ROS2 package that will monitor the health of the robot and all sensors, and restart a node if it fails.',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'watchdog_node = raccoon_watchdog.watchdog_node:main',
        ],
    },
)
