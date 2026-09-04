"""Placeholder perception node (Jetson Orin Nano, OAK-D Lite).

Subscribes to the camera image stream and logs that frames are arriving. That is
deliberately all it does — it exists to prove the depthai driver, the topic name
and the DDS link all line up before any real vision work goes in.
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

# TODO: confirm against the running driver — depthai_ros_driver topic names
#       depend on the camera name and the pipeline preset in use.
DEFAULT_IMAGE_TOPIC = '/oak/rgb/image_raw'

# Log at most one line per N frames so the console stays readable at 30 fps.
LOG_EVERY_N_FRAMES = 30


class PerceptionNode(Node):
    """Counts incoming frames and logs periodically."""

    def __init__(self):
        super().__init__('perception_node')

        self.declare_parameter('image_topic', DEFAULT_IMAGE_TOPIC)
        image_topic = self.get_parameter('image_topic').get_parameter_value().string_value

        self._frame_count = 0
        self._image_sub = self.create_subscription(
            Image, image_topic, self._on_image, 10
        )

        self.get_logger().info(f'perception_node up, subscribed to {image_topic}')

    def _on_image(self, msg: Image):
        self._frame_count += 1
        if self._frame_count % LOG_EVERY_N_FRAMES == 0:
            self.get_logger().info(
                f'{self._frame_count} frames received '
                f'({msg.width}x{msg.height}, encoding={msg.encoding})'
            )

        # TODO: convert with cv_bridge and run the actual perception pipeline:
        #       cv_image = CvBridge().imgmsg_to_cv2(msg, desired_encoding='bgr8')


def main(args=None):
    rclpy.init(args=args)
    node = PerceptionNode()
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
