# Troubleshooting

Collect diagnostics:

```bash
sudo ./support.sh
```

Check services:

```bash
sudo systemctl status skyweaver.target
sudo journalctl -u skyweaver-api -u skyweaver-capture -u skyweaver-worker -n 200
```

Check cameras:

```bash
rpicam-hello --list-cameras
v4l2-ctl --list-devices
gphoto2 --auto-detect
```
