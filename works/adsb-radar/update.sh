#!/data/data/com.termux/files/usr/bin/sh
# ADS-B 雷达一键更新 + 启动（Termux 版，走 rtl_tcp，无需 root/USB 直连）
cd ~ || exit 1
rm -rf adsbradar run.py config.json
echo "[1/4] 下载代码..."
curl -so adsb-radar-phone.tar.gz http://192.168.1.244:9090/adsb-radar-phone.tar.gz || { echo "下载失败"; exit 1; }
echo "[2/4] 解压..."
tar -xzf adsb-radar-phone.tar.gz || { echo "解压失败"; exit 1; }
echo "[3/4] 触发 rtl_tcp..."
am start -a android.intent.action.VIEW -d "iqsrc://-a 127.0.0.1 -p 1234"
sleep 2
echo "[4/4] 启动雷达..."
python run.py --source rtl_tcp --tcp-host 127.0.0.1 --tcp-port 1234
