"""Watchdog node for Jetson Orin Nano and Raspberry Pi 4B.

Step 1: Subscription plumbing and QoS compatibility only,
with no staleness detection or restart logic.
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan


DEFAULT_TOPIC = '/scan'
LOG_EVERY_N_MESSAGES = 30


class WatchdogNode(Node):
    """Counts incoming messages and logs periodically."""

    def __init__(self):
        super().__init__('watchdog_node')
        
        self.declare_parameter('topic', DEFAULT_TOPIC)
        topic = self.get_parameter('topic').get_parameter_value().string_value
        
        self._message_count = 0
        self._topic_sub = self.create_subscription(
            LaserScan, topic, self._on_message, 10
        )

        self.get_logger().info(f'watchdog_node up, subscribed to {topic}')

    def _on_message(self, msg):
        self._message_count += 1
        if self._message_count % LOG_EVERY_N_MESSAGES == 0:
            self.get_logger().info(
                f'{self._message_count} messages received'
                f'({msg.header.stamp.sec} {msg.header.stamp.nanosec})'
            )


def main(args=None):
    rclpy.init(args=args)
    node = WatchdogNode()
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