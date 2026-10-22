#!/bin/sh
set -eu
export DEBIAN_FRONTEND=noninteractive
role="$1"
apt-get update
apt-get install -y --no-install-recommends python3 python3-openpyxl virtualbox-guest-utils ca-certificates nftables
# A cloud image may use a minimal kernel without the VirtualBox guest module.
if ! modprobe vboxguest; then
  apt-get install -y --no-install-recommends linux-generic
  systemctl reboot
  exit 1
fi
install -d -m 700 /var/lib/privacy-control /var/lib/privacy-tasks /var/lib/privacy-install
chmod -R go-w /opt/privacy-bridge /opt/skill
if [ "$role" = online ]; then
  apt-get install -y --no-install-recommends xfce4 xserver-xorg lightdm lightdm-gtk-greeter dbus-x11 gnome-keyring fonts-noto-cjk xdg-utils xterm x11-utils firefox
  python3 /opt/privacy-bridge/fetch_workbuddy.py
  apt-get install -y /var/lib/privacy-install/workbuddy.deb
  rm /var/lib/privacy-install/workbuddy.deb
  chown root:root /opt/WorkBuddy/chrome-sandbox
  chmod 4755 /opt/WorkBuddy/chrome-sandbox
  install -d -o teacher -g teacher /home/teacher/PrivacyTasks /home/teacher/.config/autostart
  for root in .workbuddy .codebuddy .agents .claude; do
    install -d -o teacher -g teacher "/home/teacher/$root/skills/privacy-assistant"
    install -m 644 /opt/privacy-bridge/guest_skill.md "/home/teacher/$root/skills/privacy-assistant/SKILL.md"
  done
  # Retain the original vendor launcher and its browser sandbox.
  app=$(command -v workbuddy || command -v WorkBuddy || true)
  if [ -z "$app" ]; then
    app=$(dpkg -L workbuddy | sed -n '/\/workbuddy$/p' | head -n 1)
  fi
  test -n "$app"
  test -x "$app"
  printf '[Desktop Entry]\nType=Application\nName=WorkBuddy\nExec=%s --disable-gpu --lang=zh-CN\nTerminal=false\n' "$app" > /home/teacher/.config/autostart/workbuddy.desktop
  chown teacher:teacher /home/teacher/.config/autostart/workbuddy.desktop
  install -d /etc/lightdm/lightdm.conf.d
  printf '[Seat:*]\nautologin-user=teacher\nautologin-user-timeout=0\nuser-session=xfce\n' > /etc/lightdm/lightdm.conf.d/50-privacy.conf
  # No sudo/polkit admin membership; the Agent cannot remove firewall rules.
  gpasswd -d teacher sudo 2>/dev/null || true
  gpasswd -d teacher adm 2>/dev/null || true
  systemctl enable nftables
  nft -f /etc/nftables.conf
  python3 /opt/privacy-bridge/guest_health.py
  systemctl set-default graphical.target
else
  printf 'privacy-assistant-offline-v1\n' > /etc/privacy-assistant-offline
  chmod 600 /etc/privacy-assistant-offline
fi
systemctl enable virtualbox-guest-utils
systemctl restart virtualbox-guest-utils
# Boot-time health is inspected through Guest Control before accepting a file.
printf '{"ready":true}\n' > /var/lib/privacy-install/ready.json
