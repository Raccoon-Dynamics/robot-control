"""Placeholder hardware interface node (Raspberry Pi 4B).

#############################################################################
# TODO: THE ACTUATOR DRIVER HAS NOT BEEN CHOSEN YET.
#
# This node currently does nothing but prove the process comes up and that the
# raccoon_interfaces types resolve across the DDS link. Before it drives
# anything, pick ONE of:
#
#   1. Motor controller board over I2C/GPIO  (simplest, Pi-only, vendor lib)
#   2. MCU over serial                       (pyserial + a framing protocol)
#   3. ros2_control hardware_interface       (most work, best long-term)
#
# Whichever wins: add the dependency to package.xml (and requirements.txt if
# it is pip-only), then replace the TODO block in _on_timer() below.
#############################################################################
"""

import rclpy
from rclpy.node import Node

from raccoon_interfaces.msg import Heartbeat

HEARTBEAT_PERIOD_S = 1.0


class HardwareNode(Node):
    """Spins, logs, and publishes a Heartbeat so the Jetson can see the Pi."""

    def __init__(self):
        super().__init__('hardware_node')

        self._seq = 0
        self._heartbeat_pub = self.create_publisher(Heartbeat, 'heartbeat', 10)
        self._timer = self.create_timer(HEARTBEAT_PERIOD_S, self._on_timer)

        # TODO: subscribe to /cmd_vel (geometry_msgs/Twist) and publish
        #       /joint_states + /odom once the drivetrain exists.

        self.get_logger().info('hardware_node up (placeholder — no actuators wired)')

    def _on_timer(self):
        msg = Heartbeat()
        msg.stamp = self.get_clock().now().to_msg()
        msg.source = self.get_name()
        msg.seq = self._seq
        self._heartbeat_pub.publish(msg)

        self.get_logger().debug(f'heartbeat seq={self._seq}')
        self._seq += 1

        # TODO: read encoders / write motor commands here.


def main(args=None):
    rclpy.init(args=args)
    node = HardwareNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
