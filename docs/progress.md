# Progress Log — raccoon-dynamics

A running log of what we did, in order, and *why* — meant to double as a ROS 2 / Linux
learning reference, not just a command history. See `instructions.md` for the clean,
repeatable version of the same setup and `commands.md` for the day-to-day command lookup;
this file is the story of how we got there, mistakes included, because the mistakes are
often where the actual learning happened.

**On the dates.** Session dates are reconstructed from git commit timestamps and from ROS log
paths quoted in the entries below, so most are exact. **Sessions 2–5 are the exception** —
that work was entirely board-side (apt installs, `~/.bashrc`, netplan/NetworkManager, DDS
config) and left no commits, so it can only be bracketed between the repo scaffolding on
Sep 4 and the lidar work on Sep 10. Those four are marked approximate rather than given false
precision.

---

## Session 1 (2026-09-04) — Repo scaffolding

Before any board-side commands, Claude Code scaffolded the `raccoon-dynamics` repo's
`src/` directory: six ROS 2 packages (`raccoon_interfaces`, `raccoon_description`,
`raccoon_bringup`, `raccoon_hardware`, `raccoon_lidar`, `raccoon_perception`), each with
a `package.xml` declaring its dependencies, plus launch files, a URDF/xacro robot model,
and a `.gitignore`/`requirements.txt`. This is the code that later commands build and run
— nothing in this section was typed at a board's terminal.

**Concept:** a `package.xml` is how a ROS 2 package declares what it needs. `rosdep`
(see Part 0 below) reads these files across every package in your workspace and
translates each dependency into the right system package for your OS/architecture.

---

## Session 2 (~2026-09-04 to 09-10) — Installing ROS 2 Humble (both boards)

Run identically on the Jetson (`ryans@Philos`) and the Pi (`adam@raspi`), with one
Jetson-specific detour covered below.

### Locale setup
```bash
sudo apt update && sudo apt install -y locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8
```
**Why:** ROS 2's tooling assumes a UTF-8 locale is configured; skipping this can cause
subtle encoding issues in log output and some build tools later.

### Enable the Universe repository
```bash
sudo apt install -y software-properties-common
sudo add-apt-repository universe -y
```
**Why:** Ubuntu splits its package archive into `main` (officially supported) and
`universe` (community-maintained). Several ROS dependencies live in `universe`, so it
has to be turned on before those installs will resolve.

### Add the ROS 2 apt repository
```bash
sudo apt update && sudo apt install -y curl
export ROS_APT_SOURCE_VERSION=$(curl -s \
  https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
  | grep -F "tag_name" | awk -F\" '{print $4}')
curl -L -o /tmp/ros2-apt-source.deb \
  "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.jammy_all.deb"
sudo dpkg -i /tmp/ros2-apt-source.deb
```
**Why:** Ubuntu's own archive doesn't carry ROS packages — this adds `packages.ros.org`
as a source apt knows how to pull from, with a small `.deb` that also handles the
signing-key rotation automatically (the modern replacement for manually curl'ing a GPG
key into place).

**Lesson learned (Pi):** running `sudo apt install -y ros-humble-ros-base` right after
`dpkg -i` failed with `Unable to locate package`. `dpkg -i` only *registers* the new
source — it doesn't refresh apt's package index. The fix was just `sudo apt update`
again before the install. Small thing, easy to forget, and it'll bite again on any new
apt source you add in the future.

### Jetson-specific detour: the `nvidia-l4t-kernel` bug
Running `sudo apt update && sudo apt upgrade -y` on the Jetson triggered this, every
time it touched the L4T kernel packages:
```
Rootfs AB is not enabled.
ERROR. Procedure for A_kernel update FAILED.
```
**What this is:** a known, open bug in `nvidia-l4t-kernel`'s post-install script on
this specific JetPack 6 / L4T 36.4.7 "Devkit Super" build — its internal rootfs A/B
check fails even on the standard (non-A/B) devkit configuration. Confirmed via NVIDIA's
own developer forums as a widely-reported, still-unresolved issue, not something
specific to this board or anything we did.

**Why it's safe to ignore:** the post-install script fails *before* swapping in the new
kernel, so the currently-running kernel is untouched — the board still boots normally.
It's a `dpkg` bookkeeping problem, not a boot-chain problem.

**We tried the standard dpkg repair tools first** (safe, legitimate first move for any
half-configured package):
```bash
sudo apt --fix-broken install
sudo dpkg --configure -a
```
Both reproduced the identical error — expected, since they just re-run the same buggy
script. This confirmed the bug is deterministic, not transient.

**The actual workaround:** skip `apt upgrade` on the Jetson going forward, and install
ROS packages directly. Since ROS packages don't depend on `nvidia-l4t-kernel`, apt
happily installs them even while that package family sits broken — you just have to
read past the wall of `nvidia-l4t-*` errors and check for `Setting up <your-package>`
specifically. We verified this directly: `ros-humble-ros-base` and its entire
dependency tree (`rclcpp`, `rclpy`, `tf2`, `rosbag2`, `launch`, dozens more) all showed
`Setting up ...` successfully, with only the same seven `nvidia-l4t-*` packages in the
final error list.

**What we explicitly avoided:** `dpkg --force-overwrite` or hand-editing
`/var/lib/dpkg/status` to force the package "configured." Forcing state on a
kernel/bootloader package is the kind of move that can actually corrupt the boot chain
— not worth the risk to silence a cosmetic error.

### Install ROS 2 Humble base
```bash
sudo apt install -y ros-humble-ros-base
```
**Why `ros-base` and not `ros-desktop`:** `ros-desktop` adds GUI tools (RViz, rqt) on
top of `ros-base`. Both boards are/will be headless (SSH-only), so there's no display to
show a GUI on — `ros-base` gets the actual ROS 2 middleware and CLI tools without the
unused weight.

### Dev tools + rosdep
```bash
sudo apt install -y ros-dev-tools
sudo rosdep init
rosdep update
```
**Why two separate installs (`ros-base` then `ros-dev-tools`):** `ros-base` is the
*runtime* — what you need to run ROS 2 nodes. `ros-dev-tools` is the *build* toolchain —
`colcon` (the build system), `rosdep` (the dependency resolver), `vcstool`, and linting
tools. You don't need the build tools on a board that only runs pre-built binaries, but
we're building our own packages on both boards, so both need it.

**Lesson learned (both boards, twice):** we tried running `sudo rosdep init` before
`ros-dev-tools` was installed, and got `rosdep: command not found` both times — once on
the Jetson, once on the Pi. `rosdep` the *command* is shipped inside `ros-dev-tools`; it
doesn't exist until that package is installed. Easy mistake when working from memory
instead of checking install order — worth internalizing: **rosdep init always comes
after ros-dev-tools, never before.**

**`rosdep init` vs `rosdep update`:** `init` is a one-time, system-wide setup (needs
`sudo` because it writes to `/etc/ros/rosdep`) that tells rosdep where to find its
dependency-mapping database. `update` downloads/refreshes that database into your user
directory — no `sudo` needed, and it's the one you re-run periodically, not `init`.

### A genuine, unrelated detour: `unattended-upgrades`
Mid-session on the Pi, `sudo apt install` hung on:
```
Waiting for cache lock: Could not get lock /var/lib/dpkg/lock-frontend.
It is held by process 1366 (unattended-upgr)
```
**What this is:** Ubuntu runs an automatic background service that periodically applies
security updates on its own schedule, independent of anything you're doing. It happened
to start right as we were mid-session. apt itself was already waiting patiently — the
lines above are apt's own retry loop, not an error.

**First instinct — check if it's actually stuck or just working:**
```bash
ps aux | grep unattended-upgr
```
Watching the CPU-time column climb across repeated checks (4:32 → 5:17 → 5:56 → 6:54 →
10:49) confirmed it was genuinely working, not hung — a useful general technique for
telling "slow" from "stuck."

**Lesson learned:** we first tried `sudo systemctl stop unattended-upgrades`, which
didn't work — that's a *different*, mostly-idle systemd unit (a shutdown-guard helper)
from the one actually running the upgrade (spawned by `apt-daily-upgrade.service`).
Two similarly-named but functionally separate systemd units. The correct stop command
targets the real one: `sudo systemctl stop apt-daily-upgrade.service apt-daily.service`
— sent as SIGTERM, which the upgrade process catches and uses to finish committing
whatever package it's mid-write on before exiting, rather than dying mid-write.
**We explicitly avoided `kill -9`** on this process for the same reason as the Jetson
kernel issue above — force-killing something mid-write to `dpkg`'s database is a real
corruption risk, a slow wait is not.

In practice, it finished on its own before we needed to force anything.

---

## Session 3 (~2026-09-04 to 09-10) — Shell environment (both boards)

```bash
cat >> ~/.bashrc <<'EOF'
export RACCOON_WS=~/robot-control
source /opt/ros/humble/setup.bash
[ -f "$RACCOON_WS/install/setup.bash" ] && source "$RACCOON_WS/install/setup.bash"
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_LOCALHOST_ONLY=0
EOF
source ~/.bashrc
```
**Concepts, one at a time:**
- **`ROS_DOMAIN_ID`** partitions ROS 2 traffic the way a Wi-Fi channel number does —
  nodes only discover others on the *same* domain ID. Must match exactly on both boards,
  or they're deaf to each other even on the same network.
- **`RMW_IMPLEMENTATION`** picks which DDS (Data Distribution Service) library actually
  handles the networking under the hood — ROS 2's pub/sub layer is built on top of DDS,
  not a custom protocol. `rmw_fastrtps_cpp` is Humble's default. Also must match on both
  boards for the same reason.
- **`ROS_LOCALHOST_ONLY`** restricts a node to only talking to other nodes on the exact
  same machine when set to `1`. We need `0` — cross-board communication is the entire
  point.

> **Superseded in Session 7:** this block is now missing `export RACCOON_BOARD=pi|jetson`.
> Unlike the three above — which must be *identical* on both boards — that one must
> *differ*. Don't copy this block as-is; see Part 1 of `instructions.md`.

---

## Session 4 (~2026-09-04 to 09-10) — Verifying cross-board communication

```bash
# Jetson:
ros2 run demo_nodes_cpp talker
# Pi:
ros2 run demo_nodes_cpp listener
```
**Result: confirmed working.** The Pi printed `I heard: [Hello World: N]` messages
originating from the Jetson.

**Concept — publish/subscribe:** `talker` *publishes* messages onto a named *topic*
(`/chatter`); `listener` *subscribes* to that same topic. Neither node knows the other
exists directly — they only agree on the topic name and message type. This decoupling
(publishers and subscribers never talk to each other directly, only through topics) is
the core pattern nearly everything else in ROS 2 builds on, including the LIDAR data
later in this log.

This test also implicitly proved DDS *discovery* works: before any message can flow,
each node's DDS layer has to find the other node on the network (typically via UDP
multicast) — a separate, earlier step from the actual message delivery.

---

## Session 5 (~2026-09-04 to 09-10) — Restricting ROS 2 traffic to Ethernet only

**Why we did this:** both boards need WiFi for internet access and SSH, but by default
DDS discovery will use *any* network path it finds — including WiFi. The goal was to
make robot-control traffic use Ethernet exclusively, both for reliability (WiFi
association can drop; a dedicated wired link won't) and to keep it off a network shared
with unrelated internet traffic.

### Static IP addressing
Decided on a dedicated, WiFi-independent subnet: `10.10.10.0/24`, with the Jetson at
`10.10.10.1` and the Pi at `10.10.10.2`.

**Jetson**, via NetworkManager (JetPack has no `/etc/netplan` — it manages networking
differently from stock Ubuntu):
```bash
sudo nmcli connection add type ethernet ifname enP8p1s0 con-name eth-static \
  ipv4.method manual ipv4.addresses 10.10.10.1/24
sudo nmcli connection up eth-static
```
**Lesson learned:** a connection profile named `eth-static` already existed on
`enP8p1s0` from some earlier point — we didn't know it was there. NetworkManager warned
about the name collision but let the command through anyway, and it silently activated
the *old* profile (`192.168.1.1/24`) instead of the new one we'd just created. Found via
`nmcli -f NAME,UUID,DEVICE,ACTIVE connection show`, which lists every profile with its
UUID — the fix was deleting both by UUID and recreating a single, unambiguous one.
**Takeaway:** when a tool warns about a naming conflict rather than refusing outright,
don't assume "it worked" just because it didn't error.

**Pi**, via netplan:
```bash
sudo tee /etc/netplan/60-eth-static.yaml > /dev/null <<'EOF'
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: no
      addresses: [10.10.10.2/24]
EOF
sudo netplan apply
```
**Lesson learned:** the first attempt at this pasted the YAML content directly at the
shell prompt instead of into a file, so bash tried to execute each YAML line as a
command (`network:: command not found`, etc.). Netplan config is a *file*, not a set of
terminal commands — `tee` with a heredoc (`<<'EOF' ... EOF`) is the safe way to write
multi-line file content from a paste without bash trying to interpret it.

A `chmod 600` was added afterward, since a `netplan apply` warning revealed the config
directory was world-readable — worth catching because `/etc/netplan/50-cloud-init.yaml`
in the same directory holds the WiFi password in plaintext.

**Verified:** clean bidirectional ping, 0% loss, sub-millisecond latency, both
directions.

### Fast DDS interface whitelist — the part that actually excludes WiFi
Static IPs alone don't stop DDS from also trying WiFi — they just give Ethernet a
usable address. The actual restriction is a Fast DDS (the DDS implementation behind
`rmw_fastrtps_cpp`) configuration file that whitelists only the Ethernet interface's own
IP:
```xml
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <transport_descriptors>
    <transport_descriptor>
      <transport_id>EthOnlyTransport</transport_id>
      <type>UDPv4</type>
      <interfaceWhiteList><address>10.10.10.X</address></interfaceWhiteList>
    </transport_descriptor>
  </transport_descriptors>
  <participant profile_name="EthOnlyParticipant" is_default_profile="true">
    <rtps>
      <userTransports><transport_id>EthOnlyTransport</transport_id></userTransports>
      <useBuiltinTransports>false</useBuiltinTransports>
    </rtps>
  </participant>
</profiles>
```
(`10.10.10.1` on the Jetson, `10.10.10.2` on the Pi — **each board whitelists its own
IP**, not the other board's; the whitelist controls which local interface *this*
participant is allowed to bind to.)

Two non-obvious requirements that make the difference between this working and being
silently ignored: `is_default_profile="true"`, and `useBuiltinTransports` set to
`false` (otherwise Fast DDS falls back to its other built-in transports anyway).

Pointed at via:
```bash
export FASTRTPS_DEFAULT_PROFILES_FILE=~/dds_eth_only.xml
```

**Verified with a real negative control:** ran talker/listener, then physically
unplugged the Ethernet cable mid-run. The listener went silent immediately and resumed
the instant the cable was plugged back in — proof WiFi is structurally unreachable for
this traffic, not just unused by chance. (We deliberately tested by unplugging
Ethernet rather than disabling WiFi, since WiFi was the SSH path — disabling it would
have locked out the session doing the testing.)

---

## Session 6 (2026-09-10) — Bringing up the RPLIDAR A1

### Physical connection + identification
```bash
lsusb
```
Confirmed: `10c4:ea60 Silicon Labs CP210x UART Bridge` — a USB-to-serial adapter chip,
which is how the RPLIDAR talks to the Pi over what looks to Linux like a regular serial
port (`/dev/ttyUSB0`).

### Driver install
```bash
sudo apt install -y ros-humble-rplidar-ros
sudo usermod -aG dialout $USER
```
**Why `dialout`:** serial devices under Linux are owned by the `dialout` group by
default; adding your user to it grants permission to read/write `/dev/ttyUSB*` without
needing `sudo` for every lidar operation. **Group membership changes don't apply to an
already-open session** — this required logging out and back in before it took effect,
even though the `usermod` command itself reported success immediately.

### udev rule for a stable device name
```bash
echo 'KERNEL=="ttyUSB*", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", MODE="0666", SYMLINK+="rplidar"' \
  | sudo tee /etc/udev/rules.d/rplidar.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```
**Why this matters:** without it, the lidar could enumerate as `/dev/ttyUSB0`,
`/dev/ttyUSB1`, etc. depending on what else is plugged in and in what order — a moving
target. This rule tells udev "whenever a device with this exact vendor/product ID shows
up, also create a `/dev/rplidar` symlink pointing at it," giving a name that's stable
regardless of enumeration order.

**Lesson learned:** `udevadm trigger` is supposed to retroactively re-run rules against
devices already plugged in, but in practice it didn't create the symlink here. The
reliable fix was physically unplugging and replugging the lidar's USB cable — that
generates a genuine kernel "device added" event, which udev rules are guaranteed to
catch, unlike a retroactive trigger.

### Adding `raccoon_lidar` to the build
```bash
cd ~/robot-control
touch src/raccoon_perception/COLCON_IGNORE
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install --packages-select \
  raccoon_interfaces raccoon_description raccoon_bringup raccoon_hardware raccoon_lidar
source install/setup.bash
```
**Lesson learned:** the first build attempt failed —
`raccoon_bringup` depends on `raccoon_perception` (correctly — it's meant to coordinate
both boards), but `raccoon_perception` had never been built on the Pi, on purpose, since
that package belongs to the Jetson/OAK-D side. Colcon doesn't automatically know "this
package intentionally doesn't exist on this machine" — it just sees an unbuilt
dependency and fails. The fix, `touch .../COLCON_IGNORE`, is a per-machine marker file
telling colcon to permanently skip that package on *this* board only. It's not a code
change and doesn't belong in git — it's local machine configuration, conceptually
similar to a `.env` file.

### Launch and verify
```bash
ros2 launch raccoon_lidar rplidar.launch.py serial_port:=/dev/rplidar
```
Startup log confirmed: serial number, firmware version 1.29, hardware revision 7,
health status OK, scan mode "Standard" at a nominal 10 Hz.

> **Correction, found in Session 7:** the `serial_port:=` above was doing **nothing**.
> `rplidar.launch.py` declared no launch arguments at the time, so the port came from
> `config/rplidar.yaml` — which still said `/dev/ttyUSB0`. Everything below is real data
> from a working lidar, but it was reading `/dev/ttyUSB0`, not the `/dev/rplidar` symlink
> this command implies. Fixed in Session 7; the command now does what it says.

```bash
ros2 topic hz /scan
```
Steady ~7 Hz publish rate (a bit under the nominal 10 Hz — normal overhead from
USB/serial transfer and `topic hz`'s own averaging window, not a problem).

```bash
ros2 topic echo /scan --once
```
**Confirmed real data**, not just a heartbeat: `ranges` held a mix of `.inf` (nothing
detected at that angle, within `range_max` of 12.0m) and real floating-point distances
from 0.43m to over 1.2m — consistent with an actual room with walls and objects at
varying distances. `frame_id: laser` matched the child link name already defined in the
robot's URDF/xacro model, so this data is already sitting in a coordinate frame the rest
of the system (`raccoon_description`, eventually TF) recognizes.

**Concept — `LaserScan` message:** `angle_min`/`angle_max` define the sweep's angular
range (here, a full 360°: −π to π radians), `angle_increment` is the angular step
between readings, and `ranges` is one distance value per angle step in that sweep — the
array index encodes the angle, the value encodes the distance. `intensities` is the
signal-strength return at each point, useful later for distinguishing reflective vs.
matte surfaces.

**Result: RPLIDAR A1 fully operational**, publishing real scan data to `/scan` on the Pi.

---

## Session 7 (2026-09-10) — Folding the lidar into `bringup.launch.py`

**Goal:** stop launching the lidar by hand. `ros2 launch raccoon_bringup bringup.launch.py`
should bring it up on the Pi and not on the Jetson — from a single launch file that runs
unchanged on both boards.

### Two surprises found by reading the code before writing any

**1. `bringup.launch.py` already included `raccoon_lidar`.** The plan was to "add" the
include; it was already there. What it lacked was any notion of *which board it was on* —
the only guard was a helper that checks whether the package is installed locally:

```python
actions += _include_if_available('raccoon_lidar', 'rplidar.launch.py')
```

That works today only because of the `COLCON_IGNORE` markers from Session 6: the Jetson
never builds `raccoon_lidar`, so the lookup fails and the include is skipped. It's a real
guard, but it encodes the Pi-only intent *nowhere in the launch file* — it's an accident
of what each board happens to have built. A stale `install/` directory is enough to break
it, which is not a hypothetical (see the Part 4 warning added to `instructions.md`).

**2. `serial_port:=/dev/rplidar` had never done anything.** This is the interesting one,
because it retroactively rewrites part of Session 6. That command:

```bash
ros2 launch raccoon_lidar rplidar.launch.py serial_port:=/dev/rplidar
```

...ran cleanly and the lidar worked, so it looked correct. But `rplidar.launch.py`
declared **no launch arguments at all** — every parameter came from
`config/rplidar.yaml`, where `serial_port` was still set to `/dev/ttyUSB0`. So the lidar
was opening `/dev/ttyUSB0` the entire time. The udev symlink we built in Session 6 was
never actually being used; the setup worked because `ttyUSB0` happened to be the right
device with nothing else plugged in — exactly the fragile situation the symlink existed
to prevent.

**Concept — why ROS 2 stayed silent about it.** `ros2 launch` wraps your file in an
`IncludeLaunchDescription`, which checks that every *declared, required* argument was
supplied. It does **not** check the reverse: arguments you pass that nobody declared are
simply stored as launch configurations and ignored. So a typo'd or obsolete `name:=value`
never errors — it just quietly does nothing. Worth remembering as a general ROS 2 failure
mode: **`ros2 launch` will not tell you that an argument went unused.**

The fix was to declare a real argument and let it override the YAML:

```python
DeclareLaunchArgument('serial_port', default_value='/dev/rplidar', ...)
...
parameters=[params_file, {'serial_port': LaunchConfiguration('serial_port')}]
```

Order matters in that list: `parameters` entries are applied in sequence, so the dict
listed *after* the YAML file wins for the key they share. The YAML default was updated to
`/dev/rplidar` too, so the two agree and nobody reading the YAML is misled.

### Gating on the board — and the rewrite we did on purpose

**First attempt** used the pattern the ROS 2 docs reach for most often — evaluate a Python
expression against the environment variable:

```python
IfCondition(PythonExpression(["'", EnvironmentVariable('RACCOON_BOARD', default_value=''), "' == 'pi'"]))
```

This works. But `PythonExpression` is a literal `eval()` on a string built from an
environment variable, which means an unexpected value is a syntax error rather than a
false comparison.

**Second attempt, and what shipped**, avoids `eval` entirely by declaring a launch
argument that *defaults* from the environment, then comparing against it:

```python
DeclareLaunchArgument('board', default_value=EnvironmentVariable('RACCOON_BOARD', default_value=''))
...
condition=LaunchConfigurationEquals('board', 'pi')
```

Three things this bought beyond dropping `eval`:
- `ros2 launch ... --show-args` now documents `board` (and `serial_port`) instead of
  hiding the knob in an environment variable.
- `board:=pi` overrides the environment, so you can test the Pi path from any shell — or
  from a non-interactive SSH command, which never sources `.bashrc`.
- The argument is a normal launch configuration, so it's inspectable like any other.

**Two non-obvious requirements**, both of which are commented in the file because they
look like clutter until they bite:

- **`default_value=''` on `EnvironmentVariable` is mandatory.** Without it, an *unset*
  `RACCOON_BOARD` raises `SubstitutionFailure` and takes the entire launch down — the
  exact opposite of the "skip quietly on the other board" behaviour we wanted. Verified
  directly: without the default, unset raises; with it, unset evaluates `False`.
- **The `DeclareLaunchArgument` has to come first in the action list.** Launch visits
  actions in order, and the conditions read the value that the declaration seeds. Declare
  it after the gates and every gate silently sees an unset configuration.

**Concept — two independent guards, and why both.** The launch file now has one guard that
runs while the launch description is being *built* (is the package installed here?) and
one that runs at *execution* time (does `board` match?). The first has to stay where it is,
because `get_package_share_directory()` raises before any condition would ever be
evaluated. The second is what makes the intent explicit and survives a stale `install/`.
They answer different questions: **what got built here** vs **what should start here.**

### Verifying with no hardware and no ROS

The work happened on a Mac with no ROS 2 installed and no board access. Rather than guess,
the real ROS 2 Humble `launch` library was pip-installed from its git branch into a scratch
venv (`launch`, `ament_index_python`, plus `lark`/`pyyaml`/`osrf-pycommon`). `launch_ros`
can't be installed that way — it needs compiled `rclpy` — so only its `Node` class was
stubbed, which doesn't touch the gating logic.

Fake `share/` trees were built for a Pi image and a Jetson image, `get_package_share_directory`
was pointed at them, and the actual conditions were evaluated:

| Board image | `RACCOON_BOARD` | Result |
|---|---|---|
| Pi | `pi` | lidar starts |
| Pi | `jetson` | skipped + log line |
| Pi | unset | skipped + log line |
| Pi | `Pi` | skipped (comparison is case-sensitive) |
| Pi | unset + `board:=pi` | lidar starts |
| Jetson | `jetson` | `not installed on this board` |
| Jetson | unset | `not installed on this board` |

No case errors on either board. This is simulation, not hardware — it proves the launch
logic, not that the lidar spins.

**A deliberate choice worth recording:** the skip is *logged*, not silent. `bringup.launch.py`
prints `[bringup] raccoon_lidar skipped: board=<value> (expected 'pi')`, echoing the value
it actually saw. Because "skip quietly" is the correct behaviour across two board images, a
forgotten export is otherwise indistinguishable from a broken lidar. The log line is what
makes that difference visible in one glance.

### A git detail

`origin/main` turned out to be one commit ahead — `lidar setup on pi`, made from the Pi
itself, adding `**/COLCON_IGNORE` to `.gitignore`. It touched no shared files, so the work
was rebased on top of it rather than merged, keeping history linear. Worth a habit:
**`git fetch` and look at what's actually incoming before pushing from a second machine** —
this project now has three of them (laptop, Pi, Jetson) committing to the same branch.

---

## Session 8 (2026-09-10) — First real bringup on both boards, and one thing we chose not to fix

Session 7's board gating was written and verified in simulation on a laptop with no ROS
installed. This session ran it on the actual hardware for the first time.

### It works — and the interesting part is *how* you can tell

**(PI)**, the whole robot from one command:
```
[bringup] raccoon_perception not installed on this board — skipped.
[robot_state_publisher-1]: process started
[rplidar_node-2]: process started
[hardware_node-3]: process started
[rplidar_node-2] RPLidar health status : OK.
[rplidar_node-2] current scan mode: Standard, ... scan frequency:10.0 Hz
```

**(JETSON)**, same command, different robot:
```
[bringup] raccoon_lidar not installed on this board — skipped.
[bringup] raccoon_hardware not installed on this board — skipped.
[raccoon_perception] depthai_ros_driver not found — camera NOT started (expected off the Jetson).
[robot_state_publisher-1]: process started
[perception_node-2]: process started
```

Two details in that output are worth reading carefully, because they're the difference
between "it ran" and "it ran *for the right reason*":

- **On the Pi, the absence of a line is the evidence.** There's no
  `raccoon_lidar skipped: board=...`, which is what proves `RACCOON_BOARD=pi` was actually
  read and matched. Had the export been missing, `rplidar_node` would simply not be in that
  list and the skip line would be. Designing the skip to log its reason is what makes a
  negative result diagnosable at a glance.
- **On the Jetson, the board guard never fires at all.** Only the *package* guard prints.
  That's the two-guard structure from Session 7 behaving as designed: `_include_if_available`
  checks package presence first and returns immediately, so the `board` comparison is never
  reached for a package that isn't installed. Exactly what the simulation predicted.

`--show-args` also differs per board — the Pi lists `board` **and** `serial_port`, the Jetson
only `board`. Not a bug: `--show-args` descends into included launch files to collect their
arguments, and there's no lidar include on the Jetson to descend into.

### The `xacro` trap

First run on the Jetson died immediately:
```
[ERROR] [launch]: Caught exception in launch: file not found:
[Errno 2] No such file or directory: 'xacro'
```
The "file" is the xacro **binary**, not the `.xacro` file — `description.launch.py` shells
out to it via a `Command` substitution to expand the URDF at launch time. `ros-base` ships
`robot_state_publisher` and `urdf` but **not** `xacro`. Fixed with
`sudo apt install -y ros-humble-xacro` on both boards.

**Why it wasn't caught earlier, which is the actual lesson.** `xacro` is correctly declared
as an `exec_depend` of `raccoon_description`, so Part 2's `rosdep install` was supposed to
pull it in. Two things hid the failure:

- It's an **exec** dependency, not a build one, so `colcon build` had no reason to care.
  Everything looked green right up until launch.
- Part 2 runs rosdep with `-r`, and the runbook explicitly tells you to *expect* a wall of
  unresolved keys for the other board's sensors. A genuine failure is visually identical to
  the noise you were told to ignore. On the Jetson, the `nvidia-l4t-kernel` errors bury it
  further.

Generalisable: **when a tool's normal output is "expect errors here," you have destroyed
your ability to notice a real one.** The fix isn't to drop `-r`, it's to verify the specific
things you need afterwards — `which xacro` — rather than trusting a clean-looking exit.
Added to Part 2.

### The lidar motor: investigated, understood, deliberately not fixed

**Symptom:** the RPLIDAR spins the moment it's plugged into the Pi, whether or not any ROS
node is running.

**Why.** The A1's motor isn't driven by a scan command at all. Slamtec's USB adapter wires
it to the serial port's **DTR line** — asserted stops the motor, cleared runs it. That's a
property of the serial line state, which exists independently of whether any software has
the port open. Nothing holding the port means DTR sits cleared means the motor spins. In the
SDK, `startMotor()` on an A1 is literally "clear DTR" and `stopMotor()` is "assert DTR."

The ROS driver is already doing the right thing — the Pi log shows `Stop motor` on Ctrl-C —
but the cp210x adapter **de-asserts DTR when the last file descriptor on the port closes**,
undoing it a moment later.

Measured directly, toggling DTR from Python with the motor in view:

| Action | Motor |
|---|---|
| port opened | spinning |
| `dtr = True` (asserted) | **stopped** |
| `dtr = False` (cleared) | spinning |
| port closed while asserted | **spinning again** |

**Negative result, recorded so nobody re-derives it: `HUPCL` is not the lever.** The textbook
fix is to clear the tty's "hang up on last close" flag so the kernel stops dropping DTR. It
failed twice, for two different reasons, and both are worth knowing:

1. `sudo stty -F /dev/rplidar -hupcl` as a **separate command** can't work in principle. tty
   settings don't survive the last close, and `stty`'s own exit *is* a last close — the flag
   is gone before the next process opens the port. This is the classic reason `stty` settings
   on `/dev/ttyUSB*` "don't stick."
2. Clearing `HUPCL` via `termios` **on the live descriptor, in the same process, immediately
   before closing** still let DTR drop. So this adapter lowers DTR on last close regardless
   of the flag.

That second result is the one that closes off the whole approach: **any** udev rule or
oneshot script that opens the port, asserts DTR and exits necessarily undoes itself at close.
The only mechanism left would be a permanently-running daemon holding a descriptor open so
the last close never happens.

**Decision: leave it spinning.** The daemon would work, probably, but it means a background
service holding an fd on the primary sensor forever — with a real risk of the ROS driver
failing to open the port, and a new failure mode that presents as "the lidar is broken." The
A1 is rated for continuous rotation and is a Class 1 laser, so the actual cost of doing
nothing is some noise and roughly 100 mA. Not worth the machinery.

**The meta-lesson:** the point of the investigation wasn't the fix, it was finding out that
the cheap fixes are structurally impossible here. Knowing *why* `-hupcl` can't work is what
makes "leave it alone" an informed decision rather than giving up.

---

## Known gap (2026-09-10) — sensor liveliness and restart

**What happened:** the lidar dropped — either the device itself disconnected or the node
lost its connection to it — and the fix was to relaunch by hand. The feed simply stopped;
nothing crashed, nothing errored loudly.

**Why that distinction matters for later, not just now:** a node that silently goes dead
while still *looking* alive is a meaningfully worse failure mode than one that crashes
outright, and it gets worse the further this project goes.

- **Right now**, you're watching Foxglove — you notice the feed stall immediately, same as
  this time. Low stakes.
- **Once SLAM enters the picture**, `slam_toolbox` won't error just because `/scan` goes
  quiet — it'll keep running, keep publishing something, and either freeze the map or start
  drifting on stale data, with nothing obviously wrong on screen unless you're staring at it
  the whole session. A silent sensor dropout mid-map is a much worse debugging problem than
  this one was.
- **Once anything autonomous is involved** (Nav2, later), a robot acting on stale or absent
  `/scan` isn't an inconvenience anymore — it's a safety gap. That's the point where
  "relaunch it when you notice" stops being an acceptable answer.

**Three things worth doing, roughly in order of value-per-effort, none urgent today:**

1. **Secure the physical mount/cable.** Cheapest fix, and it addresses the actual root cause
   rather than the symptom — if the connector can't get jostled, this whole failure mode
   mostly goes away.
2. **`respawn=True` on the lidar's `Node` action.** Easy to add later, but flagging
   honestly: it likely wouldn't have caught this incident, since the process probably didn't
   exit. It only helps if the node actually dies. Worth knowing that gap rather than
   assuming it covers you.
3. **An actual liveliness watchdog** — something that tracks "no message on `/scan` for N
   seconds" and reacts (log, alert, or force a respawn), independent of whether the node
   thinks it's still alive. This is the real fix for what we just hit, and it's a genuinely
   good small first node to write by hand once the visualization step is done:
   self-contained, teaches the timer/callback pattern you'll reuse constantly in ROS 2, and
   doesn't require touching the driver internals.

**Useful while diagnosing this class of problem:** `ros2 topic hz /scan` tells you whether
data is flowing; `ros2 node list` tells you whether the node still exists; `dmesg -w` on the
Pi tells you whether the USB device physically dropped off the bus. Those three answer three
genuinely different questions, and the whole point of the failure mode above is that the
first can be silent while the second still looks healthy.

---

## Session 9 (2026-09-22) — Coming back cold: three silent failures and the laptop on Ethernet

Twelve days off. The goal was the `/scan` watchdog; most of the session went on getting back
to a working baseline, which turned out to be the more instructive part.

### The Pi couldn't find its own packages

```
Package 'raccoon_bringup' not found: "package 'raccoon_bringup' not found,
searching: ['/opt/ros/humble']"
```

The bracketed list is `AMENT_PREFIX_PATH`, and it contained **only** the ROS base install.
The workspace overlay was never sourced. A `colcon build` succeeded and changed nothing —
building and *loading* are different things, and the error was about loading.

Root cause:

```bash
$ echo "$RACCOON_WS"
/home/adam/raccoon-dynamics
```

`raccoon-dynamics` is the GitHub **org**. `robot-control` is the **repo**. `~/.bashrc` had
been pointing at a directory that never existed. And the line that consumes it is:

```bash
[ -f "$RACCOON_WS/install/setup.bash" ] && source "$RACCOON_WS/install/setup.bash"
```

A wrong path and a not-yet-built workspace produce **byte-identical silence**. Worse,
`/opt/ros/humble` still sourced normally, so `ros2` worked perfectly — which made the
problem look like anything except a missing overlay.

### The signature of an empty ROS graph

Before that was found, `ros2 topic list` on the Pi showed only `/rosout` and
`/parameter_events`. Worth knowing why: **every** node creates those two automatically,
including the short-lived node the `ros2` CLI spins up to query the graph. So those two
alone don't mean "two topics exist" — they mean the CLI is seeing its own reflection, and
nothing else is running.

### A topic that could not possibly exist

Simultaneously, the Jetson reported a live `/scan` with `Publisher count: 1` and
`Node name: rplidar_node` — while the Pi, the only machine that can physically run that
node, had an empty `ros2 node list` and couldn't even launch. Both cannot be true.

The `ros2` CLI uses a background **daemon** to cache the graph for fast queries, and it goes
stale. `ros2 topic list --no-daemon` bypasses it; `ros2 daemon stop` clears it.

**General rule worth keeping: when the ROS graph shows something impossible, suspect the
daemon before the network.**

One useful thing did come out of the phantom, though — the cached QoS was recorded from a
real publisher when one existed:

```
Reliability: RELIABLE
Durability: VOLATILE
```

`/scan` is **RELIABLE**, not the `BEST_EFFORT` that many sensor drivers use. That matters
for the watchdog: a default rclpy subscription is compatible, so there's no QoS trap here.
Had it been best-effort, a default subscriber would have registered successfully and then
received *nothing* — and the watchdog would have concluded the lidar was permanently dead.

### The pattern, now at three instances

This is becoming the signature failure mode of this project:

| Mechanism | Designed to be forgiving | What it hid |
|---|---|---|
| `ros2 launch` ignoring undeclared args | Tolerate extra arguments | `serial_port:=/dev/rplidar` did nothing for a whole session |
| `rosdep -r` | Continue past unresolvable keys | Missing `xacro` on both boards |
| `[ -f ] && source` | Skip a not-yet-built workspace | Wrong `RACCOON_WS`, unknown duration |

Each converted a real misconfiguration into silence. The project's own board-gate design
already fights this — `[bringup] raccoon_lidar skipped: board=<value>` exists precisely so a
skip announces itself and prints what it saw. **That instinct is the one to keep applying:
when you write a guard that tolerates a missing thing, make it say so.**

The concrete suggestion for `.bashrc` (not yet applied) is an `if/else` that prints a warning
when the overlay is absent. It costs one noisy line per terminal on a fresh clone before the
first build, and would have turned this session's mystery into a one-second diagnosis.

### Laptop onto the Ethernet subnet

SSH from the laptop had been going over WiFi, and a WiFi drop takes whatever is running in
the foreground down with it — which killed a session mid-work.

The laptop already had the hardware: an **AX88179B USB Gigabit adapter** on `en9`, showing a
`169.254.x.x` self-assigned address. That's the correct signature for a live link on a subnet
with **no DHCP** — which `10.10.10.0/24` deliberately is. It just needed a static address.

Two things made this non-obvious:

- **A third machine needs a switch.** A direct board-to-board cable consumes the only
  Ethernet port on each board. Pi, Jetson and laptop all plug into an unmanaged switch; since
  a dumb switch has no DHCP either, none of the existing static config changes.
- **The router field must stay blank.** In this Mac's service order the Ethernet adapter sits
  *above* Wi-Fi, so giving that service a gateway would move the default route onto a subnet
  with no internet. Blank router = a subnet route for `10.10.10.0/24` only, which is exactly
  the goal.

**Result: working.** `ssh adam@10.10.10.2` and `ssh ryans@10.10.10.1` both connect over
Ethernet, each prompting once for host-key authenticity — expected, since SSH stores keys per
hostname/IP, so a new address is a new entry even for an already-trusted machine.

**One unresolved detour on the way there.** The Pi briefly refused SSH on *every* path while
`nc -vz 10.10.10.2 22` still succeeded. That combination is itself diagnostic: TCP to port 22
completing means sshd is listening and the network is fine, so the failure was above TCP —
sshd accepting the connection but never getting a session started. Leading theory is resource
exhaustion (a full disk stops sshd forking a per-session child). A reboot cleared it and the
root cause was never confirmed, which is worth admitting rather than filing as solved. If it
returns: `df -h` and `journalctl -u ssh -n 50` **before** rebooting, since rebooting destroys
the evidence.

A second thing that muddied it: once the Pi is on both networks, mDNS advertises both
addresses, so `raspi.local` may resolve to `10.10.10.2`. "Trying WiFi instead" can silently be
the same path twice.

Also worth stating: **this changes nothing about DDS.** Each board's Fast DDS whitelist binds
that participant to its own Ethernet IP; a third machine on the subnet doesn't alter it, and
the laptop runs no ROS.

### `raccoon_watchdog` started

Scaffolded on the Pi (`ros2 pkg create --build-type ament_python`), with `package.xml` and
`setup.py` filled in. Two bugs caught on review before they could waste build cycles:

- `setup.py` used `os.path.join` and `glob` while copying only the `data_files` line from
  `raccoon_hardware` — **not** the `import os` / `from glob import glob` above it. A
  `NameError` the moment colcon executes it.
- `package.xml` had `<exex_depend>sensor_msgs</exec_depend>` — mismatched open/close tags.
  Malformed XML fails at the *parser*, before any dependency resolution, so the error names
  nothing useful.

Design decisions locked: **board-agnostic**, taking the watched topic as a parameter, so the
same package serves the lidar on the Pi and the camera on the Jetson and needs no
`COLCON_IGNORE` marker anywhere. It's in **both** boards' `--packages-select` lists.

Build order for the remaining work is in the "Known gap" section: step 1 proves QoS and
plumbing only (subscribe, count, log), and each later step is independently testable.

---

## Session 10 (2026-09-22) — Writing the first node from scratch

`raccoon_watchdog` step 1: subscribe to `/scan`, count messages, log periodically. No timer,
no staleness detection, no restart logic. The point was to prove plumbing and QoS before
building anything on top of them.

**Result: working on the Pi, and confirmed on the Jetson watching the Pi's `/scan` across
the DDS link** — which is the more interesting half, since it proves the package really is
board-agnostic rather than just claimed to be.

### Two bugs, and why each one is instructive

**`NameError: name 'callback' is not defined`.** The subscription was created with a bare
`callback` instead of `self.callback`:

```python
self._topic_sub = self.create_subscription(LaserScan, topic, callback, 10)
```

Methods live on the *instance*, not in the enclosing function's scope, so inside `__init__`
the only route to a method is through `self`. And it has to be passed **without
parentheses** — rclpy wants the function object to call later, not the result of calling it
now.

**`No executable found` — after a build that reported success.** This is the fourth entry in
this project's silent-failure collection, and the most surprising one yet: `colcon` validated
the package and had no opinion about whether the Python module existed where `setup.py`'s
entry point claimed it did. Build green, nothing to run.

The check that closes the gap:

```bash
ros2 pkg executables raccoon_watchdog     # empty = nothing registered
```

Three things produce it: a typo in the `console_scripts` string (this time's cause), the
module sitting in the **outer** `src/raccoon_watchdog/` instead of the **inner**
`src/raccoon_watchdog/raccoon_watchdog/`, or a missing `__init__.py` — without which
`find_packages()` finds nothing to install at all.

That inner/outer pair is worth internalising. `src/raccoon_watchdog/` is the **ROS package**
(holds `package.xml`, `setup.py`); `src/raccoon_watchdog/raccoon_watchdog/` is the **Python
package** (holds `__init__.py`). Same name, two different systems: colcon cares about the
first, Python's import machinery about the second. `__init__.py` — the package marker — is
unrelated to the `__init__` method despite the name.

### Naming as a design decision

The first draft used `LOG_EVERY_N_FRAMES` and `_frame_count`, inherited from
`perception_node.py`. Renamed to `LOG_EVERY_N_MESSAGES` / `_message_count`, because the node
was deliberately designed **topic-agnostic** — the same package is meant to watch a
`LaserScan` on the Pi and an `Image` on the Jetson. Camera vocabulary in a generic node would
make a future reader wonder whether it's camera-specific. Names are the cheapest place to
record a design decision.

### The Jetson lost its network mid-session

The WiFi antennas — two black U.FL pigtails — were left disconnected after the base plate
came off for the custom mount, so the Jetson effectively had no internet and couldn't reach
GitHub.

**The fix that worked, in about thirty seconds: fetch from the Pi instead of GitHub.**

```bash
git remote add pi ssh://adam@10.10.10.2/home/adam/robot-control
git fetch pi && git merge pi/main
```

**Why this is safe, which is the concept worth keeping:** git objects are content-addressed.
The commit fetched from the Pi has the identical SHA to the one on GitHub — there is no "Pi
version." When the Jetson reaches `origin` again it just updates a tracking ref. Nothing
duplicates, history doesn't fork. A peer remote is a fetch-only escape hatch; pushes still go
to `origin` (git refuses to push to a non-bare repo's checked-out branch anyway).

Two dead ends along the way, both informative:

- **`ssh: connect to host 10.10.10.3 port 22: Connection refused`** when trying the Mac as
  the peer. *Refused* is precise — the host was reached and nothing was listening. **macOS
  ships with its SSH server off.** That's a configuration state, not a fault, and it's
  categorically different from a timeout (which means something is silently dropping
  packets). The Pi already runs sshd, so the Mac route was abandoned rather than enabling
  Remote Login on a laptop that would then be SSH-reachable from WiFi too.
- **macOS Internet Sharing was rejected on purpose.** It seizes the Ethernet interface,
  forces it to `192.168.2.1` and runs its own DHCP — taking the Mac off `10.10.10.0/24`
  entirely, breaking SSH to both boards, while the boards' static addresses ignore the DHCP
  offers anyway. Sharing the Mac's connection *is* possible with `sysctl` forwarding plus a
  pf NAT anchor, keeping every static address intact, but for a temporary problem that's more
  fragile than USB-tethering a phone.

**Consequence for planning: the OAK-D is blocked.** Git-over-SSH distributes code, not apt
packages, and `ros-humble-depthai-ros` needs real internet on the Jetson. The antennas have to
go back on before that session starts.

---

## Open threads for next time

- ~~**`raccoon_watchdog` step 1**~~ — **done, Session 10.** Running on both boards, pushed,
  and confirmed cross-board (Jetson watching the Pi's `/scan`). **Next: step 2** — replace the
  counter with a last-message timestamp, add a timer that compares it to now, and log a
  warning when the gap exceeds a threshold. Still logging only, no restarts. Testable with
  `pkill rplidar_node`. Then steps 3–6 per the "Known gap" section.
- **Reattach the Jetson's WiFi antennas** — the two black U.FL pigtails, disconnected when the
  base plate came off for the custom mount. **This blocks the OAK-D**, which needs apt on the
  Jetson. Peer-fetching from the Pi covers code, not packages.
- ~~**SSH over Ethernet from the laptop**~~ — **done, Session 9.** Both boards reachable at
  `10.10.10.x`.
- **Harden the `.bashrc` overlay guard** — replace `[ -f ] && source` with an `if/else` that
  warns when the overlay is missing. Suggested in Session 9, not yet applied on either board.
- **Secure the lidar cable/mount** — still the cheapest fix for the dropout that motivated the
  watchdog, and the only one that prevents the failure rather than reacting to it.
- **OAK-D Lite** (Jetson side) — not yet connected; `raccoon_perception` still untouched.
  **Blocked on the Jetson's network** (see antennas above). When unblocked, two unverified
  assumptions in the existing code will likely need correcting, both already marked TODO:
  `oakd.launch.py` hardcodes the driver's `camera.launch.py` (some versions ship
  `rgbd_pcl.launch.py` instead), and `perception_node.py` assumes the topic
  `/oak/rgb/image_raw`, which depends on camera name and pipeline preset. The node already
  exposes an `image_topic` parameter, so retargeting needs no code change.
- **`can0` interface** on the Jetson (seen in `nmcli device status`, currently down) —
  may answer the still-open question of what drives the robot's actuators; worth
  resolving before `raccoon_hardware`'s real implementation.
- **Clock sync (`chronyc`)** — flagged as needed before any SLAM/sensor-fusion work, not
  yet actually run.
- ~~**Fold `raccoon_lidar` into `raccoon_bringup`'s default launch**~~ — **done, Session 7.**
  Gated on `RACCOON_BOARD` via a `board` launch argument.
- ~~**Set `RACCOON_BOARD` on both boards**~~ — **done on the Pi, Session 8**, proven by the
  lidar starting with no skip line. Not confirmed on the Jetson, where it isn't yet
  load-bearing: nothing is gated on `'jetson'`, so `raccoon_perception` runs off its
  package-presence guard alone. Set it there anyway for symmetry.
- **`COLCON_IGNORE` on the Jetson** (Part 4) — `raccoon_hardware` and `raccoon_lidar` still
  need their markers there. Lower urgency than it looked: the Part 4 build command uses
  `--packages-select`, which is what's *actually* keeping them off the Jetson today. The
  markers only start mattering the moment someone types a bare `colcon build`.
- ~~**Stop the lidar motor spinning when idle**~~ — **investigated and closed, Session 8.**
  Structurally not fixable without a permanent port-holding daemon; deliberately accepted.
  Don't retry `stty -hupcl`, it was tested and doesn't hold.
- **`raccoon_hardware` is not board-gated.** Deliberately left on the package-presence
  guard only, to keep Session 7's change scoped to the lidar. It takes one keyword
  (`board='pi'`) to gate it the same way — worth doing once the Jetson's stale-install
  situation is confirmed clean.
- **`RACCOON_BOARD` for non-interactive contexts** — any `systemd` unit that autostarts
  bringup will need `Environment=RACCOON_BOARD=...`, since units never source `.bashrc`.
- **Foxglove bridge** — next task, being done by hand as a learning exercise.
  *Phase A:* `sudo apt install ros-humble-foxglove-bridge` and run its own launch file
  standalone, so a WiFi/connection problem is distinguishable from a bridge problem.
  *Phase B:* fold it into `bringup.launch.py`. **Decide the gating question before writing
  it, not after:** the lidar needed `board=='pi'` because it must run on the board with the
  USB device physically attached. The bridge has no such constraint — it's a plain node
  subscribing to topics, and the shared DDS domain already makes every topic visible from
  either board (Session 4 proved that). So the real question is not "which board is this
  allowed to run on" but "do I want exactly one instance, and does it matter which board
  hosts it." Copy-pasting the lidar's gate onto a node that doesn't need it would be
  cargo-culting the pattern.
