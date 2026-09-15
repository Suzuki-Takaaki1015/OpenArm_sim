# syntax=docker/dockerfile:1
ARG ROS_BASE=ros:jazzy-ros-base-noble
FROM ${ROS_BASE}
ENV DEBIAN_FRONTEND=noninteractive
ARG ROS_APT_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu
RUN printf 'Acquire::Retries "3";\nAcquire::http::Timeout "20";\nAcquire::https::Timeout "20";\nAcquire::http::Pipeline-Depth "0";\n' > /etc/apt/apt.conf.d/99openarm-network \
    && find -L /etc/apt/sources.list.d -type f -exec sed -i "s|http://packages.ros.org/ros2/ubuntu|${ROS_APT_MIRROR}|g; s|https://packages.ros.org/ros2/ubuntu|${ROS_APT_MIRROR}|g; s|http://|https://|g; s/^Types: .*/Types: deb/; /^deb-src /d" {} + \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3-venv python3-pip ros-jazzy-rclpy ros-jazzy-sensor-msgs \
    ros-jazzy-rosgraph-msgs ros-jazzy-std-srvs \
    ros-jazzy-moveit-ros-move-group ros-jazzy-moveit-ros-visualization \
    ros-jazzy-moveit-kinematics ros-jazzy-moveit-planners-ompl \
    ros-jazzy-moveit-simple-controller-manager ros-jazzy-controller-manager \
    ros-jazzy-ros2controlcli ros-jazzy-joint-trajectory-controller ros-jazzy-joint-state-broadcaster \
    ros-jazzy-joint-state-topic-hardware-interface ros-jazzy-rviz2 \
    ros-jazzy-robot-state-publisher python3-yaml \
    libgl1 libgl1-mesa-dri libglx-mesa0 libglfw3 \
    xvfb x11vnc novnc websockify openbox x11-utils \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv --system-site-packages /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt /opt/openarm/requirements.txt
RUN pip install --no-cache-dir -r /opt/openarm/requirements.txt
COPY vendor/v1 /opt/openarm/models/v1
COPY vendor/v2 /opt/openarm/models/v2
COPY vendor/V2_MODEL_REVISION /opt/openarm/models/V2_MODEL_REVISION
COPY vendor/LICENSE /opt/openarm/models/LICENSE
COPY vendor/MODEL_REVISION /opt/openarm/models/MODEL_REVISION
COPY vendor/ycb /opt/openarm/models/ycb
COPY app /opt/openarm/app
COPY scripts /opt/openarm/scripts
RUN OPENARM_VERSION=1 OPENARM_CONFIG=/opt/openarm/config/v1 OPENARM_MODEL=/opt/openarm/models/v1/openarm_bimanual.xml python /opt/openarm/app/generate_config.py \
    && python /opt/openarm/app/prepare_v2.py \
    && OPENARM_VERSION=2 OPENARM_CONFIG=/opt/openarm/config/v2 OPENARM_MODEL=/opt/openarm/models/v2/simulation_robot.xml python /opt/openarm/app/generate_config.py
COPY README.md ENVIRONMENT.md CAMERA_MOUNT.md THIRD_PARTY.md YCB.md /opt/openarm/
RUN sed -i 's/\r$//' /opt/openarm/scripts/*.sh \
    && chmod +x /opt/openarm/scripts/*.sh \
    && useradd --create-home --uid 10001 sim \
    && dpkg-query -W > /opt/openarm/os-packages.txt \
    && pip freeze > /opt/openarm/python-packages.txt
RUN apt-get update && apt-get install -y --no-install-recommends mesa-utils python3-tk fonts-noto-cjk libosmesa6 libegl1 && rm -rf /var/lib/apt/lists/*
# OpenArm development tools
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client build-essential cmake python3-colcon-common-extensions python3-rosdep && rm -rf /var/lib/apt/lists/*
COPY demos /opt/openarm/demo_ws/src
RUN . /opt/ros/jazzy/setup.sh && cd /opt/openarm/demo_ws && colcon build --symlink-install --packages-select openarm_demos
ENV OPENARM_MODEL=/opt/openarm/models/v1/openarm_bimanual.xml \
    OPENARM_SCENE=/opt/openarm/models/v1/simulation_scene.xml \
    OPENARM_VIEWER_FPS=30 \
    LP_NUM_THREADS=2 \
    OMP_NUM_THREADS=1 \
    PYTHONPATH=/opt/openarm/app \
    PYTHONUNBUFFERED=1 \
    LIBGL_ALWAYS_SOFTWARE=1 \
    ROS_DOMAIN_ID=42 \
    ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
    DISPLAY=:99
USER sim
WORKDIR /home/sim
EXPOSE 6080
ENTRYPOINT ["/opt/openarm/scripts/entrypoint.sh"]
CMD ["web"]
