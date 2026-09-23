# Command Reference — raccoon-dynamics

Every command this project actually uses, grouped by what you're trying to do, with
**where** to run it and **when**. This is the lookup table; `instructions.md` is the
ordered runbook that explains the setup, and `progress.md` is the story of how we got
here and what we learned.

**Where tags**

| Tag | Machine |
|-----|---------|
| **(PI)** | Raspberry Pi 4B — `adam@raspi`, `10.10.10.2`. Hardware interface + RPLIDAR A1. |
| **(JET)** | Jetson Orin Nano — `ryans@Philos`, `10.10.10.1`. OAK-D Lite perception. |
| **(BOTH)** | Run on each board separately. |
| **(LAP)** | MacBook — `10.10.10.3` via the `AX88179B` USB adapter (`en9`). Editing, git, SSH. No ROS installed. |

`$RACCOON_WS` is `~/robot-control` on both boards, set by `~/.bashrc`.

---

## 1. Start of every session

| Command | Where | What it does |
|---|---|---|
| `ssh adam@10.10.10.2` | LAP | Connect to the Pi **over Ethernet** — preferred, doesn't drop with WiFi. |
| `ssh ryans@10.10.10.1` | LAP | Connect to the Jetson over Ethernet. |
| `ssh adam@raspi.local` | LAP | WiFi fallback. Use the router-assigned IP if mDNS fails. |
| `ssh ryans@philos.local` | LAP | WiFi fallback for the Jetson. |
| `echo "$RACCOON_WS"` | BOTH | Must be `~/robot-control`. `~/raccoon-dynamics` (the *org* name) is a silent failure that surfaces much later as "package not found". |
| `echo "$AMENT_PREFIX_PATH"` | BOTH | Workspace must precede `/opt/ros/humble`. If it's missing, the overlay never sourced. |
| `env \| grep -E 'ROS_\|RMW_\|FASTRTPS\|RACCOON'` | BOTH | 5-second sanity check that `.bashrc` applied. Expect `ROS_DOMAIN_ID`, `RMW_IMPLEMENTATION`, `ROS_LOCALHOST_ONLY`, `RACCOON_WS`, `RACCOON_BOARD`, `FASTRTPS_DEFAULT_PROFILES_FILE`. |
| `echo "$RACCOON_BOARD"` | BOTH | Should print `pi` or `jetson`. **Empty here is the single most likely reason the lidar doesn't start.** |
| `source ~/.bashrc` | BOTH | Re-apply the shell environment after editing `.bashrc`. New terminals do this automatically. |

> The laptop is on `10.10.10.0/24` at `.3` via a switch, and **SSH over Ethernet is
> confirmed working** to both boards. Each new address prompts once for host-key
> authenticity — normal, since SSH stores keys per hostname/IP. Passwords are unchanged;
> they belong to the account, not the network path.

---

## 2. Build the workspace

Run after **any** code change, and after every `git pull`.

| Command | Where | What it does |
|---|---|---|
| `cd "$RACCOON_WS"` | BOTH | Everything below assumes you're at the workspace root. |
| `rosdep install --from-paths src --ignore-src -r -y` | BOTH | Reads every `package.xml` and installs missing system dependencies. Re-run when a `package.xml` changes. |
| `which xacro` | BOTH | **Verify rosdep actually worked.** `-r` above continues past failures, so a real miss looks identical to the expected noise. Empty output = `sudo apt install -y ros-humble-xacro`. |
| `colcon list --names-only` | BOTH | Lists packages colcon can see here. The other board's packages should be absent (via `COLCON_IGNORE`). |
| `colcon build --symlink-install --packages-select raccoon_interfaces raccoon_description raccoon_bringup raccoon_hardware raccoon_lidar raccoon_watchdog` | PI | Build the Pi's package set. |
| `colcon build --symlink-install --packages-select raccoon_interfaces raccoon_description raccoon_bringup raccoon_perception raccoon_watchdog` | JET | Build the Jetson's package set. |
| `colcon build --symlink-install --packages-select raccoon_watchdog` | BOTH | Rebuild just the watchdog. Needed after adding a **new** `console_scripts` entry point; plain `.py` edits are live under `--symlink-install`. |
| `source install/setup.bash` | BOTH | Load the freshly built workspace into *this* shell. New terminals do it via `.bashrc`. |
| `ros2 pkg executables raccoon_watchdog` | BOTH | **What a package actually registered.** Empty output explains `No executable found` even when the build succeeded — colcon never checks that your module exists where the entry point points. |
| `rm -rf build/<pkg> install/<pkg>` | BOTH | Clear stale artifacts before rebuilding after fixing a `setup.py` entry point. |
| `touch src/<pkg>/COLCON_IGNORE` | BOTH | Mark a package as "not for this board." Per-machine, gitignored, never committed. |

> `--symlink-install` means Python, launch and YAML edits take effect **without** rebuilding
> — just relaunch. C++ changes still need a rebuild.

---

## 3. Run the robot

| Command | Where | What it does |
|---|---|---|
| `ros2 launch raccoon_bringup bringup.launch.py` | BOTH | **The main command.** Identical on both boards; each starts only what belongs to it. Pi: description + lidar + hardware. Jetson: description + perception. |
| `ros2 launch raccoon_bringup bringup.launch.py --show-args` | BOTH | List available launch arguments without starting anything. Pi shows `board` and `serial_port`; Jetson shows only `board` (no lidar include to descend into). |
| `ros2 launch raccoon_bringup bringup.launch.py board:=pi` | BOTH | Force the Pi code path, ignoring `$RACCOON_BOARD`. Use in non-interactive SSH, or to test without touching the environment. |
| `ros2 launch raccoon_bringup bringup.launch.py serial_port:=/dev/ttyUSB0` | PI | Bypass the `/dev/rplidar` udev symlink. Debugging only. |
| `ros2 launch raccoon_lidar rplidar.launch.py` | PI | Lidar **alone**, no other nodes. Defaults to `/dev/rplidar`. The right first move when isolating a sensor problem from a bringup problem. |
| `ros2 run raccoon_watchdog watchdog_node` | BOTH | Topic liveliness watchdog. Defaults to `/scan`. **Not yet part of bringup** — run it separately, alongside a running bringup. |
| `ros2 run raccoon_watchdog watchdog_node --ros-args -p topic:=/nonexistent` | BOTH | Deliberate negative test: proves the parameter is wired, and shows what "no data" looks like. |
| `Ctrl-C` | BOTH | Stops the launch. Nodes shut down in order; you'll see `process has finished cleanly`. |

**Reading the Pi's bringup output:** the *absence* of a `raccoon_lidar skipped:` line is what
proves `RACCOON_BOARD=pi` was read and matched. If you see that line instead of
`rplidar_node`, the gate rejected the board value it found — the line prints the value.

---

## 4. Inspect what's running

The core debugging toolkit. All of these work from **either** board, because the shared DDS
domain makes every topic visible across the Ethernet link.

| Command | Where | What it does |
|---|---|---|
| `ros2 node list` | BOTH | Every node currently alive, on both boards. |
| `ros2 topic list` | BOTH | Every topic being published or subscribed. |
| `ros2 topic hz /scan` | BOTH | Publish rate. **First check that a sensor is actually alive.** Expect ~7 Hz for the A1. Silence = nothing publishing. |
| `ros2 topic echo /scan --once` | BOTH | One real message. Proves actual data, not just a heartbeat. |
| `ros2 topic info /scan` | BOTH | Message type plus publisher/subscriber counts — quick way to see if anyone is listening. |
| `ros2 pkg list \| grep raccoon` | BOTH | Which of our packages are *installed* here. Catches stale `install/` artifacts. |
| `ros2 service list` | BOTH | Available services (e.g. the lidar driver's `/start_motor`, `/stop_motor`). |
| `ros2 doctor --report` | BOTH | Environment / RMW / network sanity dump. Good first move when boards can't see each other. |
| `ros2 topic list --no-daemon` | BOTH | Query the graph **bypassing the CLI's cache**. Use whenever the graph shows something impossible. |
| `ros2 daemon stop` | BOTH | Clear the stale cache. Restarts automatically on the next `ros2` command. |
| `ros2 topic info /scan --verbose` | BOTH | Full QoS of every endpoint, plus publisher/subscriber counts. **Reliability here decides what QoS a subscriber must use.** `/scan` is RELIABLE. |
| `ros2 run <pkg> <exe> --ros-args -p name:=value` | BOTH | Set a parameter for a `ros2 run` node — the equivalent of `name:=value` for `ros2 launch`. |

> **Only `/rosout` and `/parameter_events` listed?** Nothing is running. Every node creates
> those two automatically, including the CLI's own short-lived query node — you're seeing
> the CLI's reflection.

---

## 5. Lidar and serial devices (PI)

| Command | Where | What it does |
|---|---|---|
| `lsusb` | PI | Confirm the lidar is enumerated. Look for `10c4:ea60 Silicon Labs CP210x UART Bridge`. |
| `ls -l /dev/rplidar` | PI | Confirm the udev symlink exists and what `ttyUSB*` it points at. Missing = the driver will fail to open the port. |
| `sudo udevadm control --reload-rules` | PI | Apply an edited udev rule file. |
| `sudo udevadm trigger` | PI | Re-run rules against attached devices — **unreliable for new rules.** If the symlink doesn't appear, physically unplug and replug instead. |
| `groups \| grep dialout` | PI | Confirm your user can open serial ports without `sudo`. Requires a full logout after `usermod -aG dialout`. |
| `dmesg -w` | PI | Live kernel log. Shows USB attach/detach events — **the fastest way to confirm a lidar physically dropped off the bus** versus the node misbehaving. |

> **The motor spins whenever the lidar is plugged in.** Expected and deliberately not fixed;
> it's the DTR line, not software. See Part 3 of `instructions.md` — and don't retry
> `stty -hupcl`, it was tested and doesn't hold.

---

## 6. Networking and DDS

| Command | Where | What it does |
|---|---|---|
| `ping -c3 10.10.10.1` | PI | Reach the Jetson over the dedicated Ethernet link. |
| `ping -c3 10.10.10.2` | JET | Reach the Pi. |
| `ip addr show eth0` | PI | Confirm the static `10.10.10.2/24` is applied. |
| `ip addr show enP8p1s0` | JET | Confirm the static `10.10.10.1/24` is applied. |
| `ros2 multicast receive` / `ros2 multicast send` | BOTH | Pair test for DDS discovery. Receive on one board, send from the other. Hangs = multicast blocked. |
| `ros2 run demo_nodes_cpp talker` | JET | Minimal publisher, no project code involved. |
| `ros2 run demo_nodes_cpp listener` | PI | Minimal subscriber. `I heard: [Hello World: N]` = the boards are talking. **Use this to separate "network broken" from "our code broken."** |
| `nmcli -f NAME,UUID,DEVICE,ACTIVE connection show` | JET | List NetworkManager profiles with UUIDs. Catches duplicate `eth-static` profiles fighting over the interface. |
| `sudo netplan apply` | PI | Apply `/etc/netplan/60-eth-static.yaml`. |
| `chronyc tracking` | BOTH | Clock offset between boards. Skew silently breaks TF and sensor fusion. Not yet configured. |
| `networksetup -listallnetworkservices` | LAP | List macOS network services in priority order. The Ethernet adapter sitting above Wi-Fi is why its router field must stay blank. |
| `sudo networksetup -setmanual "AX88179B" 10.10.10.3 255.255.255.0 ""` | LAP | Assign the laptop's static IP. **Empty router argument is mandatory** — a gateway here hijacks the default route and kills internet. |
| `ifconfig en9 \| grep 'inet '` | LAP | Confirm `10.10.10.3`. A `169.254.x.x` address means link up but no DHCP — expected before config, wrong after. |
| `route -n get default \| grep interface` | LAP | **Must say `en0`** (Wi-Fi). If it moved to `en9`, undo the router setting. |
| `nc -vz 10.10.10.2 22` | LAP | Is SSH's port actually reachable? *Refused* = sshd not listening. *Timeout* = dropped. *Succeeded* = problem is inside SSH, not the network. |
| `sudo ss -tlnp \| grep :22` | BOTH | What address sshd is bound to. |
| `sudo ufw status` | BOTH | Firewall — a common reason TCP fails while ICMP passes. |

---

## 7. System and apt

| Command | Where | What it does |
|---|---|---|
| `sudo apt update` | BOTH | Refresh the package index. **Always run after adding an apt source** — `dpkg -i` alone doesn't. |
| `sudo apt install -y <pkg>` | BOTH | Install. On the Jetson, read past the `nvidia-l4t-*` wall and look for `Setting up <your-package>`. |
| `ps aux \| grep unattended-upgr` | BOTH | If apt is stuck on a cache lock, check whether the background upgrader is genuinely working (CPU time climbing) or hung. |
| `sudo systemctl stop apt-daily-upgrade.service apt-daily.service` | BOTH | Gracefully stop the background upgrader. **Not** `unattended-upgrades.service` — different unit, does nothing. Never `kill -9` it. |

> **JETSON:** skip `sudo apt upgrade`. The `nvidia-l4t-kernel` post-install bug fails every
> time and leaves dpkg half-configured. It's cosmetic; installing ROS packages still works.

---

## 8. Git

Three machines commit to this repo — laptop, Pi, Jetson. That makes fetching before you
push a habit worth having, not a formality.

| Command | Where | What it does |
|---|---|---|
| `git fetch origin` | ANY | Get remote state without changing your files. |
| `git log --oneline main..origin/main` | ANY | **What's incoming that you don't have.** Run this before pushing from a second machine. |
| `git status --short` | ANY | What you've changed. `COLCON_IGNORE` files never appear — they're gitignored by design. |
| `git pull --rebase` | PI / JET | Get the latest code onto a board. Rebase keeps history linear. |
| `git remote add pi ssh://adam@10.10.10.2/home/adam/robot-control` | JET | **Peer remote over Ethernet**, for when a board can't reach GitHub. Fetch-only fallback. |
| `git fetch pi && git merge pi/main` | JET | Pull commits straight from the Pi. Objects are content-addressed, so SHAs match GitHub exactly — history doesn't fork. Does **not** help with `apt`. |
| `colcon build ...` + `source install/setup.bash` | PI / JET | **Always after a pull.** Pulling changes source; it doesn't change what's installed. |

---

## 9. When something's wrong — where to start

| Symptom | First command | Then |
|---|---|---|
| Lidar didn't start under bringup | `echo "$RACCOON_BOARD"` | Empty → Part 1. Set → look for the `skipped: board=` line. |
| `/scan` has no data | `ros2 topic hz /scan` | Silent → `ros2 node list`, then `dmesg -w` for a USB drop. |
| Boards can't see each other | `ros2 run demo_nodes_cpp talker`/`listener` | Fails → `ping`, then `ros2 multicast`. Works → the problem is our code, not the network. |
| `file not found: 'xacro'` | `which xacro` | `sudo apt install -y ros-humble-xacro`. Both boards. |
| A package "should be there" | `ros2 pkg list \| grep raccoon` | Missing → rebuild. Present but shouldn't be → stale `install/`, delete it. |
| Launch behaves unexpectedly | `ros2 launch ... --show-args` | Confirms which arguments exist and their defaults. |
| `Package not found ... searching: ['/opt/ros/humble']` | `echo "$RACCOON_WS"` | Overlay not sourced. Wrong path → fix `.bashrc`. Right path → `source install/setup.bash`. |
| Graph shows something impossible | `ros2 topic list --no-daemon` | Gone without the daemon → stale cache → `ros2 daemon stop`. |
| Ping works, SSH doesn't | `nc -vz <ip> 22` | Refused → check `sshd`. Timeout → check `ufw`, then MTU, then VPN. **macOS has sshd off by default** — that's a refusal, not a fault. |
| `No executable found`, build succeeded | `ros2 pkg executables <pkg>` | Empty → entry-point typo, module in the wrong directory, or missing `__init__.py`. |
| A board can't reach GitHub | — | Fetch from the other board over Ethernet (section 8). Doesn't help `apt`. |
| SSH drops mid-build or mid-launch | — | The foreground process dies with the session. Reconnect over Ethernet (`10.10.10.x`) — it's the more stable path — and re-run. |

---

## Not yet in use

- `sudo apt install ros-humble-foxglove-bridge` — visualization, pending. Install and run
  its own launch file standalone first, so a connection problem is distinguishable from a
  bridge problem, before folding it into `bringup.launch.py`. See the open thread in
  `progress.md` for the gating question to settle first.
