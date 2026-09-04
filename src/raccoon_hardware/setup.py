import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'raccoon_hardware'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Empty glob is harmless if launch/ has no launch files yet.
        (os.path.join('share', package_name, 'launch'), glob(os.path.join('launch', '*launch.py'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Adam Zhang',
    maintainer_email='reachadamzhang@gmail.com',
    description='Robot hardware interface for the Raspberry Pi 4B.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'hardware_node = raccoon_hardware.hardware_node:main',
        ],
    },
)
