# raccoon-dynamics — Setup Runbook

**Boards**

| Tag | Board | Hostname | User | Role | Ethernet | Ethernet IP |
|-----|-------|----------|------|------|----------|--------------|
| **(PI)** | Raspberry Pi 4B | `raspi` | `adam` | robot hardware interface + RPLIDAR A1 | `eth0` | `10.10.10.2` |
| **(JETSON)** | Jetson Orin Nano | `Philos` | `ryans` | OAK-D Lite perception | `enP8p1s0` | `10.10.10.1` |
| **(LAPTOP)** | MacBook (macOS) | — | `adamzhang` | editing, git, SSH. No ROS installed. | `en9` (AX88179B USB adapter) | `10.10.10.3` |

Both boards: **Ubuntu 22.04 LTS, arm64**. Repo root (`~/robot-control`) = colcon workspace root.

> **Repo path gotcha:** the GitHub *org* is `raccoon-dynamics`; the *repo* is `robot-control`. `$RACCOON_WS` must point at `~/robot-control`. Setting it to `~/raccoon-dynamics` is a silent failure — see the callout in Part 1.

**Step tags**

| Tag | Meaning |
|-----|---------|
| `[ONCE]` | run one time per board |
| `[REPEAT]` | re-run whenever the noted thing changes |
| `[DEBUG]` | only if something is broken |

**Order:** run Claude Code first (scaffolds the repo) → commit/push → `git pull` on the other board → then follow this file top to bottom, **on each board**.

> **Virtualenvs:** You do **not** need one. ROS 2 Humble uses system Python 3.10; a venv fights colcon/ament and breaks builds. Use system Python. `requirements.txt` is only for pip-only extras (`pip install --user`), no venv.

---

## Reconnecting to the boards `[REPEAT]` — start of every session

The laptop now sits on the `10.10.10.0/24` Ethernet subnet at `10.10.10.3` via a switch (Part 6.1b). **Ethernet is the preferred SSH path** — it doesn't drop when WiFi hiccups.

```bash
ssh adam@10.10.10.2      # Pi,     over Ethernet
ssh ryans@10.10.10.1     # Jetson, over Ethernet
```

**WiFi fallback**, still works and is the path to use if the Ethernet link is down:
```bash
ssh adam@raspi.local
ssh ryans@philos.local
```

If `.local` (mDNS) resolution fails, get the WiFi IP from your router's connected-devices list (look for hostnames **Philos** and **raspi**) and SSH to that IP directly.

> **Confirmed working.** First connection to each address prompts *"The authenticity of host … can't be established"* — expected, because SSH stores host keys **per hostname/IP**, so `10.10.10.2` is a new entry even though `raspi.local` is already trusted. Answer `yes`. That is a different message from **"REMOTE HOST IDENTIFICATION HAS CHANGED"**, which means a *stored* key no longer matches and does deserve investigation.
>
> **Unexplained, and worth knowing if it recurs:** during setup the Pi refused all SSH — both paths — while `nc -vz 10.10.10.2 22` still succeeded, i.e. sshd accepted TCP but no session ever started. A reboot cleared it and the root cause was never found. That symptom pattern points at the Pi failing to *fork a session* rather than a network fault, so check `df -h` (a full disk does this) and `journalctl -u ssh -n 50` before rebooting next time.

Once in, confirm last session's environment survived (it should, via `.bashrc`, but worth a 5-second check before debugging something that isn't actually broken):
```bash
env | grep -E 'ROS_|RMW_|FASTRTPS|RACCOON'
```
Should show `ROS_DOMAIN_ID`, `RMW_IMPLEMENTATION`, `ROS_LOCALHOST_ONLY`, `RACCOON_WS`, `RACCOON_BOARD`, and — once you've done Part 6 below — `FASTRTPS_DEFAULT_PROFILES_FILE`.

> **Note the added `RACCOON` in that pattern.** `RACCOON_BOARD` does *not* contain the substring `ROS_`, so the older `'ROS_|RMW_|FASTRTPS'` filter silently hid it. An unset `RACCOON_BOARD` is precisely what makes the lidar quietly fail to start under `bringup.launch.py` (Part 7), so it belongs in the 5-second sanity check.

---

## Part 0 — Install ROS 2 Humble + dev tools  `[ONCE]` (BOTH)

Run every command on **each** board. Identical except one line (base vs desktop) and one Jetson-only caveat below.

**0.1 Locale (must be UTF-8)**
```bash
sudo apt update && sudo apt install -y locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8
```

**0.2 Enable Universe repo**
```bash
sudo apt install -y software-properties-common
sudo add-apt-repository universe -y
```

**0.3 Add the ROS 2 apt source** (current official method — self-updating key)
```bash
sudo apt update && sudo apt install -y curl
export ROS_APT_SOURCE_VERSION=$(curl -s \
  https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
  | grep -F "tag_name" | awk -F\" '{print $4}')
curl -L -o /tmp/ros2-apt-source.deb \
  "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo ${UBUNTU_CODENAME:-${VERSION_CODENAME}})_all.deb"
sudo dpkg -i /tmp/ros2-apt-source.deb
```
> **Don't forget:** `dpkg -i` only registers the new source — it does **not** refresh apt's package index. Always run `sudo apt update` again right after this, or the next step will fail with `Unable to locate package`.

**0.4 Update + upgrade** (upgrade **before** installing ROS — udev/systemd deps)
```bash
sudo apt update && sudo apt upgrade -y
```
> ⚠️ **JETSON ONLY — known issue:** on JetPack 6 / L4T 36.4.7 "Orin Nano Devkit Super" builds, `nvidia-l4t-kernel`'s post-install script has an open upstream bug and will fail with `Rootfs AB is not enabled. ERROR. Procedure for A_kernel update FAILED.` every time it's touched by an upgrade. It's cosmetic — your running kernel is untouched and the board still boots fine — but it leaves `dpkg` in a permanently half-configured state for that package family. **Recommendation: skip 0.4 entirely on the Jetson** and go straight to 0.5. ROS packages don't depend on `nvidia-l4t-kernel`, so they install cleanly regardless. See the Troubleshooting section at the bottom for what to expect if you do hit this.

**0.5 Install ROS 2 Humble** — pick **one** line per board:
```bash
# (PI) headless, no GUI:
sudo apt install -y ros-humble-ros-base

# (JETSON) also ros-base here — desktop/RViz not installed, not needed for this setup:
sudo apt install -y ros-humble-ros-base
```

**0.5b `xacro`** — required on **BOTH**, and **not** included in `ros-base`
```bash
sudo apt install -y ros-humble-xacro
which xacro          # -> /opt/ros/humble/bin/xacro
```
> **This one bit us on both boards.** `ros-base` ships `robot_state_publisher` and `urdf`, but not `xacro`. `raccoon_description/launch/description.launch.py` shells out to the `xacro` *binary* at launch time (via a `Command` substitution) to expand `raccoon.urdf.xacro` into URDF. Because it's an `exec_depend`, not a build dep, **`colcon build` succeeds** and nothing surfaces until you actually launch:
> ```
> [ERROR] [launch]: Caught exception in launch (see debug for traceback):
> file not found: [Errno 2] No such file or directory: 'xacro'
> ```
> The "file" in that message is the xacro **program**, not your `.xacro` file — a genuinely misleading error. `raccoon_description` is in the BOTH row, so this fails identically on the Pi and the Jetson and has nothing to do with board gating.

**0.6 Dev tools** (colcon, rosdep, vcstool, etc.) — BOTH
```bash
sudo apt install -y ros-dev-tools
```
> **Order matters here.** `rosdep` (the command used in 0.7) is *provided by* `ros-dev-tools`, not by `ros-base`. Running `rosdep init` before this step fails with `command not found` — easy to do by accident if you're working from memory instead of top-to-bottom. Do 0.6 before 0.7, always.

**0.7 Initialize rosdep** — BOTH (`init` is sudo; `update` is not)
```bash
sudo rosdep init          # harmless "already exists" if re-run
rosdep update
```

---

## Part 1 — Shell environment  `[ONCE]` (BOTH)

Append to `~/.bashrc` on **both** boards. `ROS_DOMAIN_ID` / `RMW_IMPLEMENTATION` / `ROS_LOCALHOST_ONLY` **must be identical** across boards or they won't discover each other. `RACCOON_BOARD` is the opposite: it **must differ**, because it's what tells `bringup.launch.py` which board it's running on. Adjust `RACCOON_WS` to your clone path.

```bash
cat >> ~/.bashrc <<'EOF'

# --- raccoon-dynamics ROS 2 env ---
export RACCOON_WS=~/robot-control        # <-- set to your repo path
source /opt/ros/humble/setup.bash
[ -f "$RACCOON_WS/install/setup.bash" ] && source "$RACCOON_WS/install/setup.bash"
export ROS_DOMAIN_ID=42                      # any 0-101, SAME on both boards
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp   # Humble default, MUST match on both
export ROS_LOCALHOST_ONLY=0                  # 0 = allow cross-board traffic
# --- end raccoon-dynamics ---
EOF
```

**Then exactly one of these — this line is different on each board:**
```bash
# (PI):
echo 'export RACCOON_BOARD=pi'     >> ~/.bashrc

# (JETSON):
echo 'export RACCOON_BOARD=jetson' >> ~/.bashrc
```

```bash
source ~/.bashrc    # apply now
echo "$RACCOON_BOARD"   # -> pi   (or jetson)
```

**Verify `RACCOON_WS` immediately — do not skip this:**
```bash
echo "$RACCOON_WS"                        # /home/<user>/robot-control
ls -l "$RACCOON_WS/install/setup.bash"    # must exist after your first build
echo "$AMENT_PREFIX_PATH"                 # workspace should precede /opt/ros/humble
```

> ⚠️ **This exact line silently broke the Pi for an entire session:**
> ```bash
> [ -f "$RACCOON_WS/install/setup.bash" ] && source "$RACCOON_WS/install/setup.bash"
> ```
> `RACCOON_WS` had been set to `~/raccoon-dynamics` — the **org** name, not the **repo** name. The path didn't exist, the `&&` guard evaluated false, and the overlay was skipped with **no message at all**. `/opt/ros/humble` still sourced fine, so `ros2` worked perfectly, which made the problem look like anything except what it was. The symptom appears much later as:
> ```
> Package 'raccoon_bringup' not found: "package 'raccoon_bringup' not found, searching: ['/opt/ros/humble']"
> ```
> **Consider making it fail loudly instead** — the warning costs you one noisy line per terminal on a fresh clone before the first build, and would have turned this into a one-second diagnosis:
> ```bash
> if [ -f "$RACCOON_WS/install/setup.bash" ]; then
>   source "$RACCOON_WS/install/setup.bash"
> else
>   echo "WARNING: no overlay at $RACCOON_WS/install/setup.bash — workspace NOT loaded"
> fi
> ```

**What `RACCOON_BOARD` does.** `bringup.launch.py` runs the same command on both boards. It declares a `board` launch argument that defaults to this variable, and gates board-specific packages on it. On the Pi, `RACCOON_BOARD=pi` is what starts the RPLIDAR. Any other value — or unset — skips those blocks and prints a log line saying so, rather than erroring. That "skip quietly" behaviour is deliberate (one launch file has to serve two board images), which is exactly why a forgotten export looks like "the lidar just didn't come up."

> ⚠️ **`~/.bashrc` is not read by non-interactive SSH.** Ubuntu's default `~/.bashrc` returns early for non-interactive shells, so `ssh adam@raspi.local 'ros2 launch raccoon_bringup bringup.launch.py'` gets **no** `RACCOON_BOARD` and silently drops the lidar. Either export it inline in the command, or override the launch argument directly:
> ```bash
> ssh adam@raspi.local 'export RACCOON_BOARD=pi; ros2 launch raccoon_bringup bringup.launch.py'
> ros2 launch raccoon_bringup bringup.launch.py board:=pi     # equivalent, no env needed
> ```
> The same applies to any `systemd` unit you write later — those need their own `Environment=RACCOON_BOARD=pi`, since they never source `.bashrc` either.

---

## Part 2 — Resolve workspace dependencies  `[REPEAT when any package.xml changes]` (BOTH)

```bash
cd "$RACCOON_WS"
rosdep install --from-paths src --ignore-src -r -y
```

`-r` keeps going past packages that can't be resolved on **this** board (e.g. depthai keys on the Pi, rplidar keys on the Jetson). That's expected — each board builds its own subset. It scans the *entire* `src/` tree regardless of what you're about to build, so seeing failures for the other board's sensor packages here is normal, not a sign something's broken.

> ⚠️ **The cost of `-r`: a real failure looks exactly like the expected noise.** This is how `xacro` (0.5b) went missing on both boards — it's a declared `exec_depend` of `raccoon_description`, rosdep was supposed to install it, and whatever went wrong scrolled past in a wall of "expected" errors. On the Jetson the `nvidia-l4t-kernel` noise (0.4) hides it even more thoroughly. Don't trust a clean-looking exit here; verify the things you actually need:
> ```bash
> which xacro                      # BOTH
> ros2 pkg list | grep -E 'rplidar|robot_state_publisher'   # (PI)
> ```

---

## Part 3 — Sensor drivers + udev  `[ONCE]`

### (PI) RPLIDAR A1 — **confirmed working setup**
```bash
sudo apt install -y ros-humble-rplidar-ros
```
> If apt can't find it: the officially documented fallback is a source build — `git clone -b ros2 https://github.com/Slamtec/rplidar_ros.git` into `src/`, then `rosdep install` + rebuild. This is a legitimate primary path, not just a last resort — arm64 apt binary availability for this package isn't guaranteed.

```bash
sudo usermod -aG dialout $USER
```
> **Log out and back in now.** Group membership doesn't apply to your current session even though the command succeeds silently — skip this and you'll hit a confusing permission error several steps later.

Confirmed device ID for this unit (via `lsusb`): **`10c4:ea60` — Silicon Labs CP210x UART Bridge**.
```bash
echo 'KERNEL=="ttyUSB*", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", MODE="0666", SYMLINK+="rplidar"' \
  | sudo tee /etc/udev/rules.d/rplidar.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
ls -l /dev/rplidar
```
> **If `/dev/rplidar` doesn't appear after `trigger`:** this happened on the real hardware — `udevadm trigger` is unreliable at retroactively applying a *new* rule to a device that was already plugged in before the rule existed. The fix is to **physically unplug and replug the lidar's USB cable**, which forces a genuine kernel attach event the rule is guaranteed to catch. Don't waste time re-running `trigger` repeatedly — go straight to the replug.

> **This symlink is now load-bearing.** Both `raccoon_lidar/config/rplidar.yaml` and the `serial_port` launch argument default to `/dev/rplidar` — not `/dev/ttyUSB0`. If the rule isn't in place, the driver fails to open the port instead of silently grabbing whatever happens to be on `ttyUSB0`. That's the intended behaviour: a loud failure beats reading a different USB serial device by accident.

**The motor spins whenever the lidar is plugged in. This is expected — accept it.**

The A1's motor is not driven by a scan command. Slamtec's USB adapter wires it to the serial port's **DTR line**: DTR asserted = motor stopped, DTR cleared = motor spinning. That's a property of the *serial line state*, which exists whether or not any software has the port open. Plug in USB with nothing holding the port, DTR sits cleared, motor spins.

The ROS driver already does the right thing — you can see it assert DTR on shutdown:
```
[rplidar_node-2] [INFO] ... [rplidar_node]: Stop motor
```
...but the cp210x adapter **de-asserts DTR when the last file descriptor on the port closes**, which undoes it a moment later. Measured on this hardware:

| Action | Motor |
|---|---|
| port opened | spinning |
| `dtr = True` (asserted) | **stopped** |
| `dtr = False` (cleared) | spinning |
| port closed while asserted | **spinning again** |

> **Negative result worth recording: `HUPCL` is not the lever.** The obvious fix is `stty -F /dev/rplidar -hupcl` to stop the kernel dropping DTR on close. It does not work here, for two compounding reasons. First, `stty` as a separate command is pointless — tty settings revert when *its own* close releases the port, so the flag is already gone before the next process opens it. Second, clearing `HUPCL` via `termios` on the live descriptor, in the same process, immediately before closing **still** let DTR drop. This adapter lowers DTR on last close regardless of the flag.
>
> That rules out any udev rule or oneshot script: anything that opens the port, asserts DTR and exits necessarily undoes itself at close. The only mechanism that would work is a permanently-running daemon holding a descriptor open so the last close never happens — **deliberately not done**, because it means a background service holding an fd on the primary sensor forever, purely to keep it quiet when idle, and it's one more thing that can fail looking like "the lidar won't open."

**Decision: leave it spinning.** The A1 is rated for continuous rotation and is a Class 1 laser, so this is bench noise and ~100 mA, not a reliability or safety issue. Unplug it if the spinning bothers you.

### (JETSON) OAK-D Lite — not yet connected
```bash
sudo apt install -y ros-humble-depthai-ros
#   If unavailable for arm64 via apt, build depthai-ros (+ depthai-core) from source.
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/80-movidius.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```
> **Plug the OAK into a USB3 (blue) port** — DepthAI streams fail/downgrade on USB2.

---

## Part 4 — Build  `[REPEAT after code changes]`

Each board only builds the packages relevant to it. `raccoon_bringup`'s `package.xml` depends on packages from **both** boards (by design, since it coordinates the whole robot) — so the packages you don't build on a given board need to be explicitly excluded, or colcon will fail looking for install artifacts that will never exist there.

**One-time per board — exclude the other board's packages:**
```bash
# (PI) — perception belongs to the Jetson:
touch "$RACCOON_WS/src/raccoon_perception/COLCON_IGNORE"

# (JETSON) — hardware + lidar belong to the Pi:
touch "$RACCOON_WS/src/raccoon_hardware/COLCON_IGNORE"
touch "$RACCOON_WS/src/raccoon_lidar/COLCON_IGNORE"
```
> `COLCON_IGNORE` is a per-machine marker file, not a code change — **do not commit it**. It's what happens locally on each board's filesystem, and it should be different on each board. The guard is already committed to `.gitignore` (`**/COLCON_IGNORE`), so `git status` will never offer you one. The flip side: these files never travel with the repo, so **a fresh clone on either board starts with none of them** and you have to recreate them by hand.

**Confirm it took:**
```bash
colcon list --names-only     # the other board's packages should NOT be listed
```

> ⚠️ **If you already built the other board's packages here, the marker alone is not enough.** `COLCON_IGNORE` stops *future* builds; it does not remove what's already in `install/`. A stale install still satisfies `get_package_share_directory()`, so `bringup.launch.py` will still consider the package present. Clear it out:
> ```bash
> # (JETSON) example — packages that belong to the Pi:
> rm -rf build/raccoon_lidar build/raccoon_hardware \
>        install/raccoon_lidar install/raccoon_hardware
> ```
> Then rebuild and re-source. Verify with `ros2 pkg list | grep raccoon`.

> **Use `COLCON_IGNORE`, not `AMENT_IGNORE`.** `raccoon_bringup`'s `package.xml` lists the board-specific packages as `exec_depend`, and relies on them still being visible under `src/` so that `rosdep --ignore-src` (Part 2) skips them. `COLCON_IGNORE` hides a package from colcon while leaving it visible to rosdep, which preserves that. `AMENT_IGNORE` would hide it from rosdep too, which would send rosdep off to resolve `raccoon_lidar` against the public index and fail. If rosdep complains anyway, `--skip-keys "raccoon_lidar raccoon_hardware"` is the escape hatch.

> **`COLCON_IGNORE` and `RACCOON_BOARD` (Part 1) are two independent guards, and you want both.** `COLCON_IGNORE` controls what gets *built* here; `RACCOON_BOARD` controls what `bringup.launch.py` *starts* here. The build guard alone leaves the board-specific intent invisible in the launch file and breaks the moment a package is built somewhere unexpected — for example a stale `install/` like the one above.

**Then build:**
```bash
cd "$RACCOON_WS"

# (PI):
colcon build --symlink-install --packages-select \
  raccoon_interfaces raccoon_description raccoon_bringup raccoon_hardware \
  raccoon_lidar raccoon_watchdog

# (JETSON):
colcon build --symlink-install --packages-select \
  raccoon_interfaces raccoon_description raccoon_bringup raccoon_perception \
  raccoon_watchdog

# Load the freshly built workspace into the current shell
# (new terminals do this automatically via ~/.bashrc):
source install/setup.bash
```

- `--symlink-install` lets you edit Python/params/launch without rebuilding.
- To skip a cloned vendor pkg on one board: drop an empty `COLCON_IGNORE` file in it (same mechanism as above).

> **`raccoon_watchdog` is board-agnostic and appears in BOTH lists.** It takes the topic to watch as a parameter, so the same package serves the lidar on the Pi and the camera on the Jetson — which means it needs **no** `COLCON_IGNORE` marker on either board. One less per-board file to keep in sync. Because these lists are explicit, a package missing from them silently never builds.

> **Note which mechanism is actually protecting you right now.** The build commands above use `--packages-select`, which already limits each board to its own list — that alone is why the Jetson reports `raccoon_lidar not installed` even if the `COLCON_IGNORE` markers were never created. The markers matter the moment you run a **bare `colcon build`** with no `--packages-select`, which is the easy thing to type. Create them anyway; belt and braces.

---

## Part 5 — Verify the two boards communicate  `[ONCE]` + `[DEBUG]`

**5.1 Clock sync — BOTH.** Ping working does **not** mean clocks agree, and skew silently breaks TF / sensor fusion later. Not yet done as of this writing — do this before any SLAM/sensor-fusion work:
```bash
sudo apt install -y chrony
chronyc tracking          # offset should be small on both; point one at the other
                          # (or both at your router/NTP) if they drift.
```

**5.2 Multicast check** — the usual failure point. WiFi APs often block multicast even when ping works; a dumb switch over Ethernet almost always passes.
```bash
# (PI):     ros2 multicast receive
# (JETSON): ros2 multicast send
#   Message arrives -> good. Hangs -> multicast blocked, use 5.4.
```

**5.3 Live talker/listener test** — **confirmed working** over the combined WiFi+Ethernet link.
```bash
sudo apt install -y ros-humble-demo-nodes-cpp     # BOTH
# (JETSON): ros2 run demo_nodes_cpp talker
# (PI):     ros2 run demo_nodes_cpp listener
#   Pi prints "I heard: [Hello World: N]" -> the boards are talking. Done.
```

**5.4 `[DEBUG]` Fallback if multicast is blocked** — Fast DDS Discovery Server (unicast). Pick one board as the server (say Jetson at `10.10.10.1`, once Part 6 below is done):
```bash
fastdds discovery -i 0 -l 10.10.10.1 -p 11811
# Then on BOTH boards, before launching nodes:
export ROS_DISCOVERY_SERVER="10.10.10.1:11811"
```

---

## Part 6 — Restrict ROS 2 traffic to Ethernet only  `[ONCE]` — **confirmed working**

**Prerequisite:** Part 5 passing first — this restricts an already-working link, it doesn't create one.

**Why:** both boards stay on WiFi for internet access and SSH, but ROS 2 discovery (DDS) will happily use *any* available network path unless told otherwise — including WiFi. This pins it to Ethernet only, so robot control traffic never touches the WiFi network.

### 6.1 Static IPs on a dedicated subnet

Works identically whether the Ethernet link is a direct board-to-board cable (current setup) or later goes through a switch — a dumb switch has no DHCP server either, so nothing here needs to change when that happens.

**(JETSON) — via NetworkManager** (JetPack has no `/etc/netplan`; check first with `nmcli device status` if interface names ever change):
```bash
sudo nmcli connection add type ethernet ifname enP8p1s0 con-name eth-static \
  ipv4.method manual ipv4.addresses 10.10.10.1/24
sudo nmcli connection up eth-static
ip addr show enP8p1s0
```
> If `nmcli connection show` reveals a duplicate `eth-static` name already exists (check with `nmcli -f NAME,UUID,DEVICE,ACTIVE connection show`), delete both old and new by UUID and recreate once, cleanly — don't leave two profiles with the same name fighting over which one activates.

**(PI) — via netplan:**
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
sudo chmod 600 /etc/netplan/60-eth-static.yaml
sudo netplan apply
ip addr show eth0
```
> Write the YAML with `tee`/heredoc as above — **don't paste YAML content directly at the shell prompt**, bash will try to execute each line as a command (`network:: command not found`, etc.).
> The `chmod 600` matters: netplan configs are readable by default, and `50-cloud-init.yaml` in the same directory has your WiFi password in it — keep the whole directory locked to owner-only.
> A `WARNING:root:Cannot call Open vSwitch: ovsdb-server.service is not running` line from `netplan apply` is normal and harmless — it's an unconditional check netplan runs regardless of whether your config uses Open vSwitch (yours doesn't).

**Confirm the link:**
```bash
ping -c3 10.10.10.1   # from Pi
ping -c3 10.10.10.2   # from Jetson
```

### 6.1b Put the laptop on the same subnet  `[ONCE]` (LAPTOP)

**Why:** SSH over WiFi drops, and a dropped SSH kills your foreground launch. Ethernet doesn't. This does **not** change anything about DDS — see the note at the end.

**Prerequisite: an unmanaged switch.** A direct board-to-board cable uses the only Ethernet port on each board; a third machine physically cannot join it. Pi, Jetson and laptop all plug into the switch. A dumb switch has no DHCP, so every device keeps its static address and nothing else changes.

The MacBook has no built-in RJ45 — it uses an **AX88179B USB Gigabit adapter**, which appears as device `en9` and as a network service literally named `AX88179B`.

```bash
networksetup -listallnetworkservices        # confirm the service name
ifconfig en9 | grep 'inet '                 # before config
```

A `169.254.x.x` address here means the link is up but no DHCP answered — **exactly what's expected** on this subnet. Assign the static address (`.1` Jetson, `.2` Pi, so the laptop takes `.3`):

```bash
sudo networksetup -setmanual "AX88179B" 10.10.10.3 255.255.255.0 ""
```

> ⚠️ **The empty router argument is the whole point.** In this Mac's service order the Ethernet adapter sits **above** Wi-Fi:
> ```
> AX88179B
> Linux for Tegra
> USB 10/100/1G/2.5G LAN
> Wi-Fi
> ```
> Give that service a gateway and macOS will prefer it for the default route — and `10.10.10.0/24` has no internet, so browsing dies instantly and confusingly. Blank router means it contributes only a subnet route for `10.10.10.0/24`, which is all you want. If the CLI rejects the empty string, use System Settings → Network → AX88179B → Details → TCP/IP → Configure IPv4: **Manually**, and leave **Router** blank.

**Verify, in this order:**
```bash
ifconfig en9 | grep 'inet '              # expect 10.10.10.3
route -n get default | grep interface    # MUST still say en0 (Wi-Fi)
ping -c3 10.10.10.1                      # Jetson
ping -c3 10.10.10.2                      # Pi
```

If the default route moved off `en0`, undo the router setting before anything else — that's the one change here that can break your internet.

> **VPNs.** This Mac has ProtonVPN and Astrill configured. An active VPN can capture routes or block local-subnet TCP. If pings pass but SSH doesn't, disconnect the VPN and retest before hunting anything else.

> **This changes nothing about ROS.** Each board's Fast DDS whitelist (6.2) binds that participant to **its own** Ethernet IP. Adding a third machine to the subnet doesn't alter that, and the laptop runs no ROS — this is purely an SSH transport improvement.

### 6.2 Fast DDS interface whitelist

This is the mechanism that actually excludes WiFi — not a preference, a hard restriction. **Each board whitelists its own Ethernet IP only** (not the other board's).

**(JETSON)** — `~/dds_eth_only.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <transport_descriptors>
    <transport_descriptor>
      <transport_id>EthOnlyTransport</transport_id>
      <type>UDPv4</type>
      <interfaceWhiteList>
        <address>10.10.10.1</address>
      </interfaceWhiteList>
    </transport_descriptor>
  </transport_descriptors>
  <participant profile_name="EthOnlyParticipant" is_default_profile="true">
    <rtps>
      <userTransports>
        <transport_id>EthOnlyTransport</transport_id>
      </userTransports>
      <useBuiltinTransports>false</useBuiltinTransports>
    </rtps>
  </participant>
</profiles>
```

**(PI)** — identical file, `~/dds_eth_only.xml`, only `<address>10.10.10.2</address>` differs.

> Two easy-to-miss requirements, confirmed necessary: `is_default_profile="true"` must be set, and `useBuiltinTransports` must be `false` — without either, the whitelist is silently ignored.

**Both boards — wire it into `~/.bashrc`:**
```bash
cat >> ~/.bashrc <<'EOF'
export FASTRTPS_DEFAULT_PROFILES_FILE=~/dds_eth_only.xml
EOF
source ~/.bashrc
```

### 6.3 Verify — including a real negative control

```bash
# (JETSON): ros2 run demo_nodes_cpp talker
# (PI):     ros2 run demo_nodes_cpp listener
```
Still works → good sign. **The real proof:** physically unplug the Ethernet cable for a few seconds while talker/listener are running. The listener should go silent immediately, then resume the moment you plug back in. (Don't test this by disabling WiFi — if that's your SSH path, you'll lock yourself out. Unplugging Ethernet is the safe version of the same test. **Confirmed working** this way.)

---

## Part 7 — Daily use  `[REPEAT]` — **confirmed working on both boards**

New terminals auto-source ROS + the workspace (Part 1) and the Ethernet-only DDS profile (Part 6). Just launch:
```bash
ros2 launch raccoon_bringup bringup.launch.py
```
**On the Pi this now starts the RPLIDAR automatically** — no standalone lidar launch and no manual `serial_port:=` needed. What comes up on each board:

| | Pi | Jetson |
|---|---|---|
| `raccoon_description` (TF tree) | yes | yes |
| `raccoon_lidar` | yes (needs `RACCOON_BOARD=pi`) | not installed |
| `raccoon_hardware` | yes | not installed |
| `raccoon_perception` | not installed | yes |

**(PI) — verified output.** The lidar comes up as part of bringup, no separate command:
```
[bringup] raccoon_perception not installed on this board — skipped.
[robot_state_publisher-1]: process started
[rplidar_node-2]: process started
[hardware_node-3]: process started
[rplidar_node-2] RPLidar health status : OK.
[rplidar_node-2] current scan mode: Standard, ... scan frequency:10.0 Hz
```
**The absence of a `raccoon_lidar skipped:` line is the signal that `RACCOON_BOARD=pi` is set correctly.** If the gate had failed you'd see that line instead of `rplidar_node`.

**(JETSON) — verified output:**
```
[bringup] raccoon_lidar not installed on this board — skipped.
[bringup] raccoon_hardware not installed on this board — skipped.
[raccoon_perception] depthai_ros_driver not found — camera NOT started (expected off the Jetson).
[robot_state_publisher-1]: process started
[perception_node-2]: process started
```
Note the Jetson prints only the *package* guard (`not installed`), never the board guard. That's by design: the presence check runs first and returns immediately, so the `board` comparison is never reached for a package that isn't there. Consequence worth knowing — **`RACCOON_BOARD` is not currently load-bearing on the Jetson**, since nothing is gated on `'jetson'` yet. Set it anyway (Part 1) so the two boards stay symmetric and it's already correct when something is.

The third line is expected until the OAK-D is physically connected and `depthai_ros_driver` is installed (Part 3).

Inspect or override the board without touching your environment:
```bash
ros2 launch raccoon_bringup bringup.launch.py --show-args
ros2 launch raccoon_bringup bringup.launch.py board:=pi     # force the Pi path
ros2 launch raccoon_bringup bringup.launch.py serial_port:=/dev/ttyUSB0   # bypass the udev symlink
```
> `--show-args` output **differs per board, correctly**. The Pi lists both `board` and `serial_port`; the Jetson lists only `board`. That's because `--show-args` descends into included launch files to collect their arguments, and on the Jetson there is no `raccoon_lidar` include to descend into. A short list on the Jetson is not a missing argument — it's the same guard working.
The standalone lidar launch still works unchanged, for debugging one sensor in isolation:
```bash
ros2 launch raccoon_lidar rplidar.launch.py                        # defaults to /dev/rplidar
ros2 launch raccoon_lidar rplidar.launch.py serial_port:=/dev/ttyUSB0
```
Handy checks:
```bash
ros2 node list          # who's up
ros2 topic list         # what's being published
ros2 topic hz <topic>   # publish rate — good first check that a sensor is alive
ros2 topic echo <topic> --once   # one sample of real data, not just a heartbeat
ros2 doctor --report    # env / RMW sanity check
```

---

## Part 8 — Optional: C++ toolchain & ros2_control  `[ONCE]` (only if using C++)

You already have most of it: `ros-base` ships `rclcpp`, and `ros-dev-tools` brings colcon + cmake. `raccoon_interfaces` already generates C++ **and** Python bindings — no change there.

**8.1 Toolchain** — BOTH
```bash
sudo apt install -y build-essential cmake ccache gdb   # ccache/gdb optional but recommended
```

**8.2 If `raccoon_hardware` goes C++:** recreate it as `ament_cmake` (not `ament_python`). Its `package.xml` should `<depend>` on at least: `rclcpp`, `rclcpp_components`. A `ros2_control` hardware interface additionally depends on `hardware_interface` and `pluginlib`.

**8.3 If using `ros2_control`** (recommended once you want the standard controller stack + Nav2) — install on the board running the hardware (PI):
```bash
sudo apt install -y ros-humble-ros2-control ros-humble-ros2-controllers \
  ros-humble-hardware-interface ros-humble-controller-manager \
  ros-humble-diff-drive-controller ros-humble-joint-state-broadcaster
```
Trade-off: a plain `rclcpp` node is less setup for a simple serial motor controller; `ros2_control` is more scaffolding but gives you `diff_drive_controller`, odometry, and clean Nav2 integration for free. **Open question:** the Jetson has a `can0` interface present (currently down) — if that's how the actuators will be driven, it points toward a CAN-based motor controller (e.g. ODrive/VESC-style), which changes what `raccoon_hardware` needs to depend on. Resolve this before committing to a hardware-interface design.

**8.4 Pi compile-speed notes.** C++ builds are slow on the Pi 4B (4 cores, limited RAM).
- `ccache` (installed above) caches object files across rebuilds — big win.
- If a build OOMs, cap parallelism: `colcon build --parallel-workers 2`.
- `--symlink-install` still helps for the Python/launch/param parts of a mixed package.

---

## Troubleshooting quickref  `[DEBUG]`

- **Boards can't see each other's nodes:**
  - `ROS_DOMAIN_ID` and `RMW_IMPLEMENTATION` identical on both? (`echo` them)
  - `ROS_LOCALHOST_ONLY=0` on both?
  - Multicast blocked → Part 5.4 discovery server.
  - Firewall up → `sudo ufw disable` on a trusted LAN, or open the DDS UDP ports.
- **Both Ethernet AND WiFi up** → resolved for this project via Part 6's Fast DDS whitelist, which structurally excludes WiFi rather than just hoping DDS picks the right interface.
- **`command not found: ros2`** → new shell didn't source; check the `~/.bashrc` block (Part 1).
- **`Package '<pkg>' not found ... searching: ['/opt/ros/humble']`** → **the workspace overlay is not sourced in this shell.** That bracketed list is `AMENT_PREFIX_PATH`; your workspace isn't in it. Immediate fix: `source install/setup.bash`. Root cause is almost always a wrong `$RACCOON_WS` — `echo "$RACCOON_WS"` and confirm it's `~/robot-control`, not `~/raccoon-dynamics` (Part 1). Note the build itself succeeds fine; this is purely a "not loaded" problem.
- **`ros2 topic list` shows only `/rosout` and `/parameter_events`** → **nothing is running.** Both topics are created automatically by *every* node, including the short-lived one the `ros2` CLI spins up to query the graph — so seeing only those two means the CLI is looking at its own reflection. Start bringup.
- **The graph shows a node or topic that cannot possibly exist** (e.g. `/scan` with a publisher while the Pi is demonstrably idle) → **stale `ros2` daemon cache.** The CLI uses a background daemon to make graph queries fast, and it goes stale. Confirm and clear:
  ```bash
  ros2 topic list --no-daemon      # bypasses the cache entirely
  ros2 daemon stop                 # restarts automatically on next use
  ```
  General rule: when the ROS graph shows something impossible, suspect the daemon before the network.
- **Ping works but SSH doesn't, over the `10.10.10.x` link** → ping proves the IP layer only; SSH is TCP/22 and fails independently. Work down this ladder:
  1. `nc -vz 10.10.10.2 22` from the laptop. *Refused* = sshd isn't listening on that address. *Timeout* = something is dropping TCP. *Succeeded* = the port is fine and the problem is inside SSH.
  2. On the board (over the WiFi path, which still works): `sudo ss -tlnp | grep :22` and `sudo ufw status`.
  3. `ssh -vvv adam@10.10.10.2` — where it stops tells you which phase failed.
  4. If it hangs during key exchange specifically, suspect **MTU**: `ping -c3 -D -s 1472 10.10.10.2`. Small packets passing while large ones fail is the classic signature, common with USB Ethernet adapters.
  5. Disconnect any VPN on the laptop and retest.
- **`No executable found`** from `ros2 run`, with a **successful build** → the package built, but no executable was registered. `colcon` validates package structure and has no opinion on whether your Python module exists where the entry point claims. The check that closes that gap:
  ```bash
  ros2 pkg executables raccoon_watchdog      # empty = entry point never installed
  ```
  Three causes, in order of likelihood: a **typo in the `console_scripts` string** in `setup.py` (it must read `exe_name = python_package.module:function`); the module file sitting in the **outer** `src/<pkg>/` instead of the **inner** `src/<pkg>/<pkg>/` Python package; or a **missing `__init__.py`**, without which `find_packages()` finds nothing to install. After fixing, clear stale artifacts before rebuilding: `rm -rf build/<pkg> install/<pkg>`.
- **A board can't reach GitHub** (e.g. the Jetson with its WiFi antennas detached) → you don't need the internet, you need the commits, and the other board already has them. Add a peer remote over the Ethernet link:
  ```bash
  # on the Jetson
  git remote add pi ssh://adam@10.10.10.2/home/adam/robot-control
  git fetch pi && git merge pi/main
  ```
  Commits are content-addressed, so the objects fetched from a peer are **identical** to the ones on GitHub — same SHAs. When the board reaches `origin` again it simply updates the tracking ref; nothing duplicates and history doesn't fork. Keep the peer remote as a permanent fetch-only fallback, and always **push** to `origin` (git refuses to push to a non-bare repo's checked-out branch anyway).
  > This does **not** help with `apt`. Installing packages still needs real internet on that board.
- **Jetson WiFi is extremely weak or absent** → check whether the two black **antenna pigtails** are still attached to the M.2 WiFi card. They're U.FL connectors that snap on with straight-down pressure, and they live in the base plate — easy to leave disconnected after any chassis work. `nmcli device wifi list` seeing *nothing at all* (rather than weak networks) suggests the card itself came loose instead.
  > **Do not use macOS Internet Sharing to work around this.** It seizes the Ethernet interface, forces it to `192.168.2.1` and runs its own DHCP — which takes your Mac off `10.10.10.0/24` entirely and breaks SSH to the boards, while the boards' static addresses ignore the DHCP offers. If you need the Mac as a gateway, do it surgically: `sysctl net.inet.ip.forwarding=1` plus a pf NAT anchor, keeping every static address intact. USB-tethering a phone to the Jetson is usually less work.
- **`command not found: rosdep`** → `ros-dev-tools` (Part 0.6) hasn't been installed yet, or wasn't installed before you tried `rosdep init`. Install it first, then retry.
- **rosdep errors on one board** → expected for the other board's sensor keys; `-r` in Part 2 lets it continue. Only worry if **your** board's packages fail to resolve.
- **`file not found: [Errno 2] No such file or directory: 'xacro'`** on `ros2 launch` → `ros-humble-xacro` isn't installed; `ros-base` does not include it. `sudo apt install -y ros-humble-xacro` (Part 0.5b). The missing "file" is the xacro *binary*, not your `.xacro` file. Affects **both** boards, since `raccoon_description` runs on both — and it's a runtime-only dependency, so `colcon build` passes cleanly right up until you launch.
- **LIDAR permission denied on `/dev/ttyUSB0`** → you didn't log out/in after `usermod` (Part 3).
- **`bringup.launch.py` comes up but the lidar doesn't, no error** → this is the designed behaviour when `RACCOON_BOARD` isn't `pi`. Look for the log line `[bringup] raccoon_lidar skipped: board=... (expected 'pi')`, which prints the value it actually saw. Then: `echo "$RACCOON_BOARD"` (Part 1). If it's empty in an SSH one-liner but correct in an interactive shell, that's the non-interactive `.bashrc` trap — see the callout in Part 1. Quick confirmation that nothing else is wrong: `ros2 launch raccoon_bringup bringup.launch.py board:=pi`.
- **`[bringup] raccoon_lidar not installed on this board — skipped.`** → different problem from the one above. This is the *package* guard, not the board guard: `raccoon_lidar` isn't in this board's `install/`. Expected on the Jetson. On the Pi it means the build didn't include it (Part 4).
- **Lidar starts but opens the wrong device / fails to open `/dev/rplidar`** → the udev rule isn't in place or didn't fire (Part 3). Both the YAML and the launch argument now default to `/dev/rplidar`, so a missing symlink is a hard failure rather than a silent fallback. `ls -l /dev/rplidar` to check; unplug/replug to fix.
- **A package you `COLCON_IGNORE`d still shows up in `ros2 pkg list`** → stale `build/`/`install/` artifacts from before the marker existed. `COLCON_IGNORE` only prevents future builds; delete the directories by hand (Part 4).
- **LIDAR spins constantly, even with no ROS node running** → expected, not a fault. A1 motor state follows the serial DTR line, and the adapter clears DTR whenever the last fd on the port closes. Investigated and deliberately not fixed — see the callout in Part 3. Don't burn time on `stty -hupcl`; it was tested and doesn't hold.
- **New udev rule doesn't create the symlink even after `udevadm trigger`** → physically unplug and replug the device. `trigger` is unreliable for retroactively applying a rule to something already attached; a real attach event always works.
- **OAK-D not detected / low res** → USB2 port or missing udev rule (Part 3).
- **`colcon build` fails looking for another package's install artifacts** (e.g. `raccoon_bringup` failing on a missing `raccoon_perception/package.sh`) → that package needs a `COLCON_IGNORE` marker on this board. See Part 4.
- **Jetson: `apt install`/`upgrade` always shows a wall of `nvidia-l4t-kernel` errors** → known, open, cosmetic upstream bug on this JetPack build (see Part 0.4 callout). Check for `Setting up <your-package>` and confirm your package isn't in the final `Errors were encountered while processing:` list — if it's not, the install succeeded despite the noise. Avoid `dpkg --force-overwrite` or manually editing `/var/lib/dpkg/status` to "fix" this — that risks the boot chain for no real benefit.
- **`apt install` hangs on "Waiting for cache lock... held by process NNNN (unattended-upgr)"** → Ubuntu's automatic background security-update service grabbed the lock first. Don't force-kill it (risks corrupting a mid-write package). Check `ps aux | grep unattended-upgr` — if CPU time is climbing, it's actively working; let it finish, or `sudo systemctl stop apt-daily-upgrade.service apt-daily.service` for a graceful stop (note: **not** `unattended-upgrades.service` itself — that's a separate, unrelated shutdown-guard unit and stopping it does nothing).
- **`needrestart` shows a "Daemons using outdated libraries" dialog** → normal after any apt operation that updates a shared library a running service uses. Accept the default selection, Tab to `<Ok>`, Enter. Can be silenced permanently (optional): `echo "\$nrconf{restart} = 'a';" | sudo tee /etc/needrestart/conf.d/50-autorestart.conf`.
- Give each board a **unique hostname + static IP** — already done via Part 6 for the Ethernet link.
