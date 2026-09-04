# Liveness beacon. Every long-running Raccoon node publishes one of these so the
# other board can tell whether its peer is alive without probing it.

# Time the heartbeat was produced (node clock).
builtin_interfaces/Time stamp

# Node or subsystem that produced it, e.g. "hardware_node", "perception_node".
string source

# Monotonically increasing counter, reset on node start. Gaps == dropped packets.
uint32 seq
